"""Fila supervisionada de um contato de teste no Windows; sem envio."""
import os
import time
from . import config
from .monitor_whatsapp import SCRIPT, recentes
from .previa_motor import PreviaMotor

UNREAD = r'''
const rows=[...document.querySelectorAll('#pane-side [role="row"]')];
const matches=rows.filter(r=>r.querySelector('span[title]')?.getAttribute('title')===arguments[0]);
if(matches.length!==1) return {count:matches.length,element:null,unread:false};
const row=matches[0];
const unread=[...row.querySelectorAll('[aria-label]')].some(n=>/mensage[^\n]*n[aã]o lid|unread/i.test(n.getAttribute('aria-label')||''));
return {count:1,element:row.querySelector('span[title]'),unread};
'''

def run():
    import msvcrt
    from selenium import webdriver
    from selenium.common.exceptions import StaleElementReferenceException
    from selenium.webdriver.chrome.options import Options
    if os.getenv('WHATSAPP_ENVIAR', '0') != '0':
        raise SystemExit('Esta fila aceita somente WHATSAPP_ENVIAR=0.')
    preview = PreviaMotor(os.getenv('WHATSAPP_CONTATOS_TESTE', ''), os.getenv('WHATSAPP_NOME_TESTE', ''))
    profile = config.ARQUIVO_CONHECIMENTO.parent / 'whatsapp-perfil'
    profile.mkdir(parents=True, exist_ok=True)
    options = Options()
    options.add_argument('--user-data-dir=' + str(profile.resolve()))
    options.add_argument('--profile-directory=Default')
    options.add_argument('--start-maximized')
    options.page_load_strategy = 'eager'
    driver = None
    try:
        driver = webdriver.Chrome(options=options)
        driver.set_page_load_timeout(90)
        driver.get('https://web.whatsapp.com')
        deadline = time.time() + 300
        while not driver.execute_script("return !!document.querySelector('#pane-side');"):
            if time.time() > deadline:
                raise RuntimeError('Lista nao encontrada em 300 segundos.')
            time.sleep(2)
        since = time.time()
        start = time.strftime('%H:%M', time.localtime((int(since)//60+1)*60))
        seen = set()
        armed = False
        paused = False
        resume = False
        previous = None
        print('FILA AUTOMATICA DE TESTE - PREVIA SEM ENVIO.', flush=True)
        print('Contato permitido: ' + preview.nome + '. Telefone informado manualmente, NAO verificado pelo programa.', flush=True)
        print('Deixe o contato visivel na lista. Nao precisa abrir a conversa.', flush=True)
        print('Envie mensagem nova pelo outro celular A PARTIR DE ' + start + '.', flush=True)
        print('CONTROLE NO TERMINAL: P pausa; R retoma e reabre o contato de teste. Sem Enter. Ctrl+C encerra.', flush=True)
        print('Trocar de contato depois da abertura automatica pausa, mas nao fecha o Chrome. Abrir conversa pode marcar como lida.', flush=True)
        while True:
            key = msvcrt.getwch().lower() if msvcrt.kbhit() else ''
            if key == 'p':
                paused = True
                armed = False
                preview.pausada = True
                print('FILA PAUSADA pelo terminal. Nenhum clique automatico. Pressione R no terminal para retomar.', flush=True)
            elif key == 'r' and paused:
                paused = False
                armed = False
                resume = True
                since = time.time()
                seen.clear()
                start = time.strftime('%H:%M', time.localtime((int(since)//60+1)*60))
                print('RETOMADA AUTORIZADA. Mensagens do intervalo pausado serao ignoradas. Novo teste A PARTIR DE ' + start + '.', flush=True)
            if paused:
                time.sleep(0.5)
                continue
            state = driver.execute_script(SCRIPT)
            if not state['online'] or not state['list']:
                raise RuntimeError('Lista/rede indisponivel. Reinicie para novo marco; sem retomada automatica.')
            if armed and state['name'] != preview.nome:
                paused = True
                armed = False
                preview.pausada = True
                print('FILA PAUSADA: voce mudou de conversa ou o cabecalho ficou indisponivel. Chrome permanece aberto. Nenhum clique ate R no terminal.', flush=True)
                continue
            candidate = driver.execute_script(UNREAD, preview.nome)
            element = candidate['element']
            notice = 'Aguardando nao lidas do contato autorizado na lista carregada.'
            if candidate['count'] > 1:
                notice = 'Nome duplicado na lista; selecao bloqueada.'
                armed = False
            elif element is not None and (candidate['unread'] or resume):
                try:
                    element.click()
                except StaleElementReferenceException:
                    time.sleep(2)
                    continue
                deadline = time.time() + 10
                while True:
                    state = driver.execute_script(SCRIPT)
                    if state['name'] == preview.nome:
                        armed = True
                        if resume:
                            preview.pausada = False
                            resume = False
                        break
                    if time.time() > deadline:
                        break
                    time.sleep(0.5)
                if not armed:
                    paused = True
                    preview.pausada = True
                    print('FILA PAUSADA: cabecalho nao confirmou o clique. Nenhum processamento. R no terminal para tentar novamente.', flush=True)
                    continue
                print('Conversa de teste aberta automaticamente. Sem envio.', flush=True)
            if armed and candidate['count'] == 1:
                state = driver.execute_script(SCRIPT)
                if not state['online'] or not state['list']:
                    raise RuntimeError('Lista/rede perdida durante leitura.')
                if state['name'] != preview.nome:
                    paused = True
                    armed = False
                    preview.pausada = True
                    print('FILA PAUSADA: conversa mudou durante leitura. Nenhum processamento. R no terminal para retomar.', flush=True)
                    continue
                fresh, missing = recentes(state['rows'], seen, since, time.time())
                notice = 'Fila ativa: lendo apenas o contato de teste; sem envio.'
                if missing:
                    notice += ' Ha elementos sem horario reconhecido; ignorados.'
                if any(r['direction'] == 'saida' for r in fresh):
                    paused = True
                    armed = False
                    preview.pausada = True
                    print('FILA PAUSADA: mensagem propria recente detectada. Nenhuma previa deste lote. Chrome aberto; R no terminal para retomar.', flush=True)
                    continue
                for row in fresh:
                    text = row['text'].strip()
                    if not text:
                        continue
                    print(time.strftime('%H:%M:%S') + ' | ' + preview.nome + ' | ' + row['direction'] + ' | ' + text, flush=True)
                    print('LEITURA | evidencia=' + row['evidence'], flush=True)
                    if row['direction'] == 'desconhecida':
                        print('Direcao desconhecida; motor nao consultado.', flush=True)
                    preview.processar(preview.nome, row['direction'], text)
            if notice != previous:
                print(notice, flush=True)
                previous = notice
            time.sleep(2)
    except KeyboardInterrupt:
        print('Fila parada.', flush=True)
    finally:
        preview.close()
        if driver is not None:
            try:
                driver.quit()
            except (Exception, KeyboardInterrupt):
                print('Feche somente a janela antiga do bot se ainda estiver aberta.', flush=True)

if __name__ == '__main__':
    run()
