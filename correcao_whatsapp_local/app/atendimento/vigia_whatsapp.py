"""Vigia conservador: somente numeros visiveis autorizados, texto e mensagens novas.
Nao atende nomes salvos nem IDs @lid. Se a estrutura da pagina divergir, nao envia.
"""
from __future__ import annotations
import argparse
import json
import os
import re
import time
from datetime import datetime
from pathlib import Path
from . import config, ponte_whatsapp as ponte

PERFIL = config.ARQUIVO_CONHECIMENTO.parent / "whatsapp-perfil"
ESTADO = config.ARQUIVO_CONHECIMENTO.parent / "whatsapp-vigia-seguro.json"

def timestamp(autor):
    # Somente formato local brasileiro explicitamente reconhecido.
    m = re.match(r"^\[(\d{1,2}):(\d{2}),\s*(\d{1,2})/(\d{1,2})/(\d{4})\]", autor or "")
    if not m:
        return None
    h, minute, d, month, year = map(int, m.groups())
    try:
        return datetime(year, month, d, h, minute).timestamp()
    except ValueError:
        return None

def options():
    from selenium.webdriver.chrome.options import Options
    op = Options()
    PERFIL.mkdir(parents=True, exist_ok=True)
    op.add_argument(f"--user-data-dir={PERFIL.resolve()}")
    op.add_argument("--profile-directory=Default")
    op.add_argument("--start-maximized")
    return op

def titles(driver):
    return driver.execute_script("return [...new Set([...document.querySelectorAll('#pane-side span[title]')].map(e=>e.getAttribute('title')))];") or []

def opened(driver, numero):
    names = driver.execute_script("return [...document.querySelectorAll('#main header span[title]')].map(e=>e.getAttribute('title'));") or []
    for name in names:
        try:
            if ponte.normalizar_contato(name) == numero:
                return True
        except ValueError:
            pass
    return False

def messages(driver):
    return driver.execute_script("""
      return [...document.querySelectorAll('#main [data-id]')].slice(-30).map(e=>{
        const a=e.querySelector('[data-pre-plain-text]');
        const t=e.querySelector('.selectable-text');
        return {id:e.getAttribute('data-id'),
          incoming:!!(e.matches('.message-in') || e.closest('.message-in') || e.querySelector('.message-in')),
          outgoing:!!(e.matches('.message-out') || e.closest('.message-out') || e.querySelector('.message-out')),
          autor:a?a.getAttribute('data-pre-plain-text'):'', texto:t?t.innerText:''};
      });
    """) or []

def eligible(msg, numero, since, seen):
    ident = msg.get('id') or ''
    # Falhar fechado: precisa confirmar direcao e destinatario pelo ID.
    if not msg.get('incoming') or msg.get('outgoing'):
        return False
    if not ident.startswith('false_' + numero + '@c.us_'):
        return False
    ts = timestamp(msg.get('autor'))
    return bool(ident not in seen and ts is not None and since < ts <= time.time()
                and (msg.get('texto') or '').strip())

def main():
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    parser = argparse.ArgumentParser()
    parser.add_argument('--login', action='store_true')
    args = parser.parse_args()
    live = os.getenv('WHATSAPP_ENVIAR', '0') == '1'
    allowed = set()
    for value in os.getenv('WHATSAPP_CONTATOS_TESTE', '').split(','):
        if value.strip():
            allowed.add(ponte.normalizar_contato(value))
    if not args.login and not allowed:
        raise SystemExit('Defina WHATSAPP_CONTATOS_TESTE com numeros internacionais autorizados.')
    seen = set()
    if ESTADO.exists():
        try:
            seen = set(json.loads(ESTADO.read_text(encoding='utf-8'))['vistos'])
        except (ValueError, KeyError, TypeError):
            raise SystemExit('Estado invalido; nao iniciado por seguranca.')
    def remember(ident):
        seen.add(ident)
        tmp = ESTADO.with_suffix('.tmp')
        tmp.write_text(json.dumps({'vistos': sorted(seen)}), encoding='utf-8')
        tmp.replace(ESTADO)
    driver = webdriver.Chrome(options=options())
    try:
        driver.get('https://web.whatsapp.com')
        print('Aguardando login. Nao use esta janela para atendimento manual.')
        deadline = time.time() + 300
        while not titles(driver):
            if time.time() > deadline:
                raise RuntimeError('Lista nao encontrada: login ou seletores precisam de revisao.')
            time.sleep(2)
        if args.login:
            print('Login concluido. Nenhuma mensagem enviada.')
            return
        since = time.time()
        print('Modo:', 'ENVIO PARA NUMEROS AUTORIZADOS' if live else 'SIMULACAO SEM ENVIO')
        print('Horario sem segundos no WhatsApp: so aceita mensagens a partir do proximo minuto.')
        while True:
            # Sem reconexao automatica: perder a lista encerra esta execucao.
            names = titles(driver)
            if not names:
                raise RuntimeError('Conexao/lista perdida. Reinicie para criar novo marco.')
            for name in names:
                try:
                    numero = ponte.normalizar_contato(name)
                except ValueError:
                    continue
                if numero not in allowed:
                    continue
                driver.execute_script("""
                  const e=[...document.querySelectorAll('#pane-side span[title]')].find(e=>e.getAttribute('title')===arguments[0]);
                  if(e) e.click();
                """, name)
                time.sleep(1)
                if not opened(driver, numero):
                    continue
                rows = messages(driver)
                if not rows:
                    continue
                last = rows[-1]
                if not eligible(last, numero, since, seen):
                    continue
                remember(last['id'])
                if not live:
                    print('Mensagem nova elegivel (simulacao, sem consultar motor).')
                    continue
                st = ponte.status(numero)
                if st.get('estado') in ('humano', 'aguardando_humano'):
                    continue
                result = ponte.receber(numero, last['texto'], nome=name)
                answer = '\n\n'.join(result['respostas']).strip()
                if not answer:
                    continue
                time.sleep(1)
                # Verificar destinatario, ultima mensagem e estado novamente.
                current = messages(driver)
                st = ponte.status(numero)
                if (not opened(driver, numero) or not current
                    or current[-1]['id'] != last['id']
                    or st.get('estado') in ('humano', 'encerrada')):
                    print('Envio descartado: contexto mudou.')
                    continue
                boxes = driver.find_elements(By.CSS_SELECTOR, '#main footer div[contenteditable="true"]')
                if len(boxes) != 1:
                    continue
                box = boxes[0]
                if box.text.strip():
                    print('Rascunho existente: envio descartado.')
                    continue
                box.click()
                lines = answer.splitlines()
                for i, line in enumerate(lines):
                    if i:
                        box.send_keys(Keys.SHIFT, Keys.ENTER)
                    box.send_keys(line)
                if not opened(driver, numero):
                    raise RuntimeError('Destinatario mudou durante digitacao; revise o rascunho.')
                box.send_keys(Keys.ENTER)
                print('Resposta enviada ao numero autorizado.')
            time.sleep(6)
    finally:
        driver.quit()

if __name__ == '__main__':
    main()
