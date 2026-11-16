"""Transporte Selenium para a ponte existente. Teste supervisionado, um contato."""
import argparse
import json
import os
import time
from . import config, ponte_whatsapp as ponte
from .vigia_whatsapp import identidade, horario
from ..database import Base, engine

def snapshot(driver):
    return driver.execute_script("""
      const header = document.querySelector('#main header');
      const headers = header ? header.innerText.split(String.fromCharCode(10)).map(s=>s.trim()).filter(Boolean) : [];
      return {headers,
      rows:[...document.querySelectorAll('#main [data-id]')].slice(-30).map(e=>{
        const a=e.matches('[data-pre-plain-text]')?e:e.querySelector('[data-pre-plain-text]');
        const t=e.querySelector('.selectable-text');
        const media=!!e.querySelector('audio,video,img[src^="blob:"],[data-icon="audio-play"],[data-icon="document"]');
        return {id:e.getAttribute('data-id'),autor:a?a.getAttribute('data-pre-plain-text'):'',texto:t?t.innerText:'',media};
      })};
    """)

def current(driver, name, phone, ident):
    state = snapshot(driver)
    if name not in state['headers'] or not state['rows']:
        return False
    last = state['rows'][-1]
    remote, error = identidade(last['id'])
    return not error and remote == phone and last['id'] == ident

def run():
    from selenium import webdriver
    from selenium.common.exceptions import SessionNotCreatedException
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    parser = argparse.ArgumentParser()
    parser.add_argument('--login', action='store_true')
    args = parser.parse_args()
    live = os.getenv('WHATSAPP_ENVIAR', '0') == '1'
    phone = name = ''
    if not args.login:
        phone = ponte.normalizar_contato(os.getenv('WHATSAPP_CONTATOS_TESTE', ''))
        name = os.getenv('WHATSAPP_NOME_TESTE', '').strip() or input('Nome EXATO do contato de teste na lista: ').strip()
        if not name:
            raise SystemExit('Nome obrigatorio.')
    profile = config.ARQUIVO_CONHECIMENTO.parent / 'whatsapp-perfil'
    profile.mkdir(parents=True, exist_ok=True)
    options = Options()
    options.add_argument('--user-data-dir=' + str(profile.resolve()))
    options.add_argument('--profile-directory=Default')
    options.add_argument('--start-maximized')
    options.page_load_strategy = 'eager'
    try:
        driver = webdriver.Chrome(options=options)
    except SessionNotCreatedException:
        raise SystemExit('Chrome nao iniciou. Feche a janela anterior do bot e tente novamente. Nao apague o perfil. Se persistir, e necessario diagnosticar Chrome/driver; esta mensagem nao identifica a causa.')
    try:
        driver.set_page_load_timeout(90)
        driver.get('https://web.whatsapp.com')
        print('Aguardando lista. Nenhum envio durante login.', flush=True)
        deadline = time.time() + 300
        while not driver.execute_script("return !!document.querySelector('#pane-side');"):
            if time.time() > deadline:
                raise RuntimeError('Login/lista nao encontrados em 300 segundos.')
            time.sleep(2)
        if args.login:
            print('Login concluido. Nenhum envio.')
            return
        Base.metadata.create_all(bind=engine)
        since = time.time()
        path = config.ARQUIVO_CONHECIMENTO.parent / 'whatsapp-local-vistos.json'
        seen = set()
        if path.exists():
            seen = set(json.loads(path.read_text(encoding='utf-8'))['vistos'])
        def mark(ident):
            seen.add(ident)
            tmp = path.with_suffix('.tmp')
            tmp.write_text(json.dumps({'vistos':sorted(seen)}), encoding='utf-8')
            tmp.replace(path)
        print('Modo: ' + ('ENVIO AO CONTATO AUTORIZADO' if live else 'SIMULACAO SEM ENVIO'), flush=True)
        print('Espere o proximo minuto e envie mensagem nova. Nao use esta janela para conversar.', flush=True)
        previous = None
        while True:
            if not driver.execute_script("return !!document.querySelector('#pane-side');"):
                raise RuntimeError('Lista perdida: encerrado. Reinicie para novo marco.')
            count = driver.execute_script("return [...document.querySelectorAll('#pane-side span[title]')].filter(e=>e.getAttribute('title')===arguments[0]).length;", name)
            log = 'Contato ausente da lista visivel ou nome duplicado; aguardando.'
            if count == 1:
                driver.execute_script("const e=[...document.querySelectorAll('#pane-side span[title]')].find(e=>e.getAttribute('title')===arguments[0]);if(e)e.click();", name)
                time.sleep(1)
                state = snapshot(driver)
                log = 'Cabecalho ou mensagens nao confirmados.'
                if name in state['headers'] and state['rows']:
                    last = state['rows'][-1]
                    remote, error = identidade(last['id'])
                    stamp = horario(last['autor'])
                    log = error or 'Aguardando mensagem nova do numero autorizado.'
                    if not error and remote != phone:
                        log = 'Numero diferente do autorizado; bloqueado.'
                    elif not error and stamp is None:
                        log = 'Horario nao reconhecido; bloqueado.'
                    elif (not error and remote == phone and stamp is not None
                          and since < stamp <= time.time() and last['id'] not in seen
                          and not last['media'] and 0 < len(last['texto'].strip()) <= 4000):
                        mark(last['id'])
                        if not live:
                            log = 'SUCESSO: contato salvo e mensagem nova confirmados. Sem envio e sem consultar motor.'
                        else:
                            status = ponte.status(phone)
                            if status.get('estado') in ('humano', 'aguardando_humano'):
                                log = 'Conversa com atendimento humano; nenhuma resposta automatica.'
                            elif not current(driver, name, phone, last['id']):
                                log = 'Conversa mudou; mensagem descartada.'
                            else:
                                result = ponte.receber(phone, last['texto'], nome=name)
                                answer = '\n\n'.join(result['respostas']).strip()
                                status = ponte.status(phone)
                                if (answer and status.get('estado') not in ('humano', 'encerrada')
                                    and current(driver, name, phone, last['id'])):
                                    boxes = driver.find_elements(By.CSS_SELECTOR, '#main footer div[contenteditable="true"]')
                                    if len(boxes) != 1 or boxes[0].text.strip():
                                        raise RuntimeError('Caixa ausente ou rascunho existente. Nada enviado; revise manualmente.')
                                    box = boxes[0]
                                    box.click()
                                    try:
                                        for i, line in enumerate(answer.splitlines()):
                                            if i:
                                                box.send_keys(Keys.SHIFT, Keys.ENTER)
                                            box.send_keys(line)
                                        status = ponte.status(phone)
                                        if (status.get('estado') in ('humano', 'encerrada')
                                            or not current(driver, name, phone, last['id'])):
                                            raise RuntimeError('Contexto mudou durante digitacao; parei sem pressionar Enter. Revise rascunho.')
                                        box.send_keys(Keys.ENTER)
                                    except Exception:
                                        print('Envio interrompido; revise qualquer rascunho antes de continuar.', flush=True)
                                        raise
                                    log = 'Resposta do motor existente enviada ao contato autorizado.'
                                else:
                                    log = 'Sem resposta ou contexto alterado; nenhum envio.'
            if log != previous:
                print(log, flush=True)
                previous = log
            time.sleep(5)
    finally:
        driver.quit()

if __name__ == '__main__':
    try:
        run()
    except KeyboardInterrupt:
        print('Atendimento parado.')
