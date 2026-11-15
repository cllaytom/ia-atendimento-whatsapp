"""Diagnostico de contatos salvos. Sem envio e sem chamada ao motor."""
import argparse
import os
import re
import time
from datetime import datetime
from . import config

def identidade(value):
    match = re.fullmatch(r'(true|false)_(\d+)@(c\.us|s\.whatsapp\.net|lid|g\.us)_(.+)', value or '')
    if not match:
        return None, 'Identificador nao reconhecido; bloqueado.'
    direction, remote, domain, _ = match.groups()
    if domain == 'lid':
        return None, 'ID @lid: nao foi possivel confirmar o telefone; bloqueado.'
    if domain == 'g.us':
        return None, 'Grupo ignorado.'
    if direction != 'false':
        return None, 'Mensagem propria ignorada.'
    if not 12 <= len(remote) <= 15:
        return None, 'Telefone invalido; bloqueado.'
    return remote, None

def horario(value):
    match = re.match(r'^\[\s*(\d{1,2}):(\d{2}),\s*(\d{1,2})/(\d{1,2})/(\d{4})\s*\]', value or '')
    if not match:
        return None
    h, minute, day, month, year = map(int, match.groups())
    try:
        return datetime(year, month, day, h, minute).timestamp()
    except ValueError:
        return None

def main():
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    parser = argparse.ArgumentParser()
    parser.add_argument('--login', action='store_true')
    args = parser.parse_args()
    if os.getenv('WHATSAPP_ENVIAR', '0') != '0':
        raise SystemExit('Use WHATSAPP_ENVIAR=0. Envio bloqueado nesta versao de diagnostico.')
    expected = os.getenv('WHATSAPP_CONTATOS_TESTE', '').strip()
    name = ''
    if not args.login:
        if not re.fullmatch(r'\d{12,15}', expected):
            raise SystemExit('Configure somente um numero internacional em WHATSAPP_CONTATOS_TESTE.')
        name = os.getenv('WHATSAPP_NOME_TESTE', '').strip() or input('Nome EXATO do contato salvo na lista: ').strip()
        if not name:
            raise SystemExit('Nome vazio.')
    profile = config.ARQUIVO_CONHECIMENTO.parent / 'whatsapp-perfil'
    profile.mkdir(parents=True, exist_ok=True)
    options = Options()
    options.add_argument('--user-data-dir=' + str(profile.resolve()))
    options.add_argument('--profile-directory=Default')
    options.add_argument('--start-maximized')
    options.page_load_strategy = 'eager'
    driver = webdriver.Chrome(options=options)
    try:
        driver.set_page_load_timeout(90)
        driver.get('https://web.whatsapp.com')
        print('Aguardando lista de conversas. SEM ENVIO.', flush=True)
        deadline = time.time() + 300
        while not driver.execute_script("return !!document.querySelector('#pane-side');"):
            if time.time() > deadline:
                raise RuntimeError('Lista nao encontrada em 300 segundos.')
            time.sleep(2)
        if args.login:
            print('Lista encontrada. Nenhum envio.')
            return
        since = time.time()
        seen = set()
        previous = None
        print('DIAGNOSTICO SEM ENVIO: espere o proximo minuto e envie mensagem nova.', flush=True)
        while True:
            if not driver.execute_script("return !!document.querySelector('#pane-side');"):
                raise RuntimeError('Lista perdida. Reinicie para novo marco; nao ha retomada automatica.')
            count = driver.execute_script("return [...document.querySelectorAll('#pane-side span[title]')].filter(e=>e.getAttribute('title')===arguments[0]).length;", name)
            log = 'Contato nao encontrado na parte visivel da lista.'
            if count > 1:
                log = 'Nome duplicado: bloqueado.'
            elif count == 1:
                driver.execute_script("const e=[...document.querySelectorAll('#pane-side span[title]')].find(e=>e.getAttribute('title')===arguments[0]);if(e)e.click();", name)
                time.sleep(1)
                headers = driver.execute_script("return [...document.querySelectorAll('#main header span[title]')].map(e=>e.getAttribute('title'));") or []
                log = 'Cabecalho nao confirmado; bloqueado.'
                if name in headers:
                    rows = driver.execute_script("""
                      return [...document.querySelectorAll('#main [data-id]')].slice(-30).map(e=>{
                        const a=e.matches('[data-pre-plain-text]')?e:e.querySelector('[data-pre-plain-text]');
                        const t=e.querySelector('.selectable-text');
                        return {id:e.getAttribute('data-id'),autor:a?a.getAttribute('data-pre-plain-text'):'',texto:t?t.innerText:''};
                      });
                    """) or []
                    log = 'Nenhuma mensagem com identificador encontrada.'
                    if rows:
                        last = rows[-1]
                        remote, error = identidade(last.get('id'))
                        stamp = horario(last.get('autor'))
                        if error:
                            log = error
                        elif remote != expected:
                            log = 'Telefone diferente do autorizado: bloqueado.'
                        elif stamp is None:
                            log = 'Telefone confirmado; horario nao reconhecido (esperado HH:MM, DD/MM/AAAA).'
                        elif stamp <= since:
                            log = 'Telefone confirmado; mensagem anterior ao inicio: ignorada.'
                        elif stamp > time.time():
                            log = 'Horario futuro: bloqueado.'
                        elif not (last.get('texto') or '').strip():
                            log = 'Mensagem sem texto: ignorada.'
                        elif last['id'] in seen:
                            log = 'Mensagem ja detectada; aguardando outra.'
                        else:
                            seen.add(last['id'])
                            log = 'SUCESSO: contato salvo + telefone confirmado + mensagem nova. NENHUM ENVIO.'
            if log != previous:
                print(log, flush=True)
                previous = log
            time.sleep(5)
    finally:
        driver.quit()

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('Diagnostico encerrado.')
