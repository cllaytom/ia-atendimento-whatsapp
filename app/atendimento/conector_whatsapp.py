"""Conector local supervisionado. Execute com python -m app.atendimento.conector_whatsapp."""
from __future__ import annotations
import json
import os
import re
import time
from pathlib import Path
from urllib.parse import urlparse
import httpx
from ..config import API_KEY, BASE_DIR
from .vigia_whatsapp import identidade, horario

JS_ROWS = """
return [...document.querySelectorAll('#main [data-id]')].map(e=>{
 const a=e.matches('[data-pre-plain-text]')?e:e.querySelector('[data-pre-plain-text]');
 const t=e.querySelector('.selectable-text');
 return {id:e.getAttribute('data-id'),autor:a?a.getAttribute('data-pre-plain-text'):'',texto:t?t.innerText:''};
});
"""

def telefone(rows):
    numeros = {identidade(r.get('id'))[0] for r in rows if (r.get('id') or '').startswith('false_')}
    numeros.discard(None)
    return next(iter(numeros)) if len(numeros) == 1 else None

def salvar(path, vistos):
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(sorted(vistos)), encoding='utf-8')
    tmp.replace(path)

def main():
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    base = os.getenv('WHATSAPP_API_URL', 'http://127.0.0.1:8033').rstrip('/')
    if urlparse(base).hostname not in ('127.0.0.1', 'localhost', '::1'):
        raise RuntimeError('Use uma API local; chave nao enviada a outros hosts.')
    live = os.getenv('WHATSAPP_ENVIAR', '0') == '1'
    dados = Path(BASE_DIR) / 'dados'
    perfil = dados / 'whatsapp-perfil'
    perfil.mkdir(parents=True, exist_ok=True)
    arquivo = dados / 'conector-whatsapp-vistos.json'
    vistos = set(json.loads(arquivo.read_text(encoding='utf-8'))) if arquivo.exists() else set()
    options = Options()
    options.add_argument('--user-data-dir=' + str(perfil.resolve()))
    options.add_argument('--profile-directory=Default')
    options.add_argument('--start-maximized')
    with httpx.Client(base_url=base, headers={'X-API-Key': API_KEY}, timeout=300, trust_env=False) as api:
        def chamar(method, rota, **kwargs):
            resposta = api.request(method, rota, **kwargs)
            resposta.raise_for_status()
            return resposta.json()
        chamar('GET', '/atendimento/config')
        driver = webdriver.Chrome(options=options)
        try:
            driver.get('https://web.whatsapp.com')
            deadline = time.time() + 300
            while not driver.find_elements(By.CSS_SELECTOR, '#pane-side'):
                if time.time() > deadline:
                    raise RuntimeError('Login/lista indisponivel.')
                time.sleep(2)
            inicio = time.time()
            print('ENVIO ATIVO' if live else 'PREVIA: nao consulta motor nem envia', flush=True)
            print('Use janela exclusiva. Assuma clientes pelo painel antes de responder. Aguarde o proximo minuto.', flush=True)
            while True:
                if not driver.find_elements(By.CSS_SELECTOR, '#pane-side'):
                    raise RuntimeError('Lista perdida; reinicie apos conferir a conexao.')
                nomes = driver.execute_script("return [...new Set([...document.querySelectorAll('#pane-side span[title]')].map(e=>e.title))];") or []
                for nome in nomes:
                    abriu = driver.execute_script("const a=[...document.querySelectorAll('#pane-side span[title]')].filter(e=>e.title===arguments[0]);if(a.length!==1)return false;a[0].click();return true;", nome)
                    if not abriu:
                        continue
                    time.sleep(1)
                    rows = driver.execute_script(JS_ROWS) or []
                    numero = telefone(rows)
                    if not numero:
                        continue
                    novas = []
                    for r in rows:
                        remoto, _ = identidade(r.get('id'))
                        stamp = horario(r.get('autor'))
                        if remoto == numero and r['id'] not in vistos and stamp and inicio < stamp <= time.time() and (r.get('texto') or '').strip():
                            novas.append(r)
                    if not novas:
                        continue
                    if not live:
                        vistos.update(r['id'] for r in novas)
                        salvar(arquivo, vistos)
                        print('Entrada detectada; previa sem envio.', flush=True)
                        continue
                    texto = '\n'.join(r['texto'] for r in novas)
                    if len(texto) > 4000:
                        raise RuntimeError('Lote acima de 4000 caracteres; tratar manualmente.')
                    # Marca antes da chamada: falha ambigua encerra, sem repetir automaticamente.
                    vistos.update(r['id'] for r in novas)
                    salvar(arquivo, vistos)
                    resultado = chamar('POST', '/whatsapp/receber', json={'contato': numero, 'nome': nome, 'texto': texto})
                    resposta = '\n\n'.join(resultado.get('respostas') or []).strip()
                    if not resposta:
                        continue
                    atual = driver.execute_script(JS_ROWS) or []
                    if telefone(atual) != numero or [r['id'] for r in atual] != [r['id'] for r in rows]:
                        raise RuntimeError('Conversa mudou durante processamento; resposta nao enviada.')
                    estado = chamar('GET', '/whatsapp/status/' + numero)
                    if estado.get('estado') in ('humano', 'encerrada'):
                        continue
                    if estado.get('estado') == 'aguardando_humano' and resultado.get('estado') != 'aguardando_humano':
                        continue
                    boxes = driver.find_elements(By.CSS_SELECTOR, '#main footer div[contenteditable="true"]')
                    if len(boxes) != 1 or boxes[0].text.strip():
                        raise RuntimeError('Campo indisponivel ou com rascunho; envio cancelado.')
                    box = boxes[0]
                    box.click()
                    for i, linha in enumerate(resposta.splitlines()):
                        if i:
                            box.send_keys(Keys.SHIFT, Keys.ENTER)
                        box.send_keys(linha)
                    atual = driver.execute_script(JS_ROWS) or []
                    estado = chamar('GET', '/whatsapp/status/' + numero)
                    if telefone(atual) != numero or [r['id'] for r in atual] != [r['id'] for r in rows] or estado.get('estado') in ('humano', 'encerrada'):
                        raise RuntimeError('Contexto mudou; revise o rascunho antes de continuar.')
                    box.send_keys(Keys.ENTER)
                    print('Enter acionado; entrega nao confirmada. Sem repeticao automatica.', flush=True)
                time.sleep(3)
        finally:
            driver.quit()

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('Conector parado.')
