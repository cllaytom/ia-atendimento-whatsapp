"""Monitor local somente leitura. Nao confirma telefone nem envia respostas."""
import json
import os
import time
from . import config

SCRIPT = '''
const root = document.querySelector('#main');
const header = root && root.querySelector('header');
const name = header ? header.innerText.split(String.fromCharCode(10)).map(s=>s.trim()).filter(Boolean)[0] : '';
function wrapper(e) {
  const body = e.querySelector('.selectable-text');
  const block = (body || e).closest('.focusable-list-item');
  return block && root.contains(block) && block.querySelectorAll('[data-pre-plain-text]').length===1 ? block : null;
}
function signature(block) {
  return block ? [...block.classList].sort().join(' ') : '';
}
const labels = new Map();
let hasIn=false, hasOut=false;
if(root) for(const block of root.querySelectorAll('.focusable-list-item')) {
  if(block.querySelectorAll('[data-pre-plain-text]').length!==1) continue;
  const inbound=!!block.querySelector('[data-icon="tail-in"]');
  const outbound=!!block.querySelector('[data-icon="tail-out"]');
  if(inbound===outbound) continue;
  hasIn=hasIn||inbound; hasOut=hasOut||outbound;
  const key=signature(block);
  if(!labels.has(key)) labels.set(key,new Set());
  labels.get(key).add(inbound?'entrada':'saida');
}
const rows = root ? [...root.querySelectorAll('[data-id]')].map(e=>{
  const body = e.querySelector('.selectable-text');
  const icons = [...e.querySelectorAll('[data-icon]')].map(n=>n.getAttribute('data-icon'));
  const incoming = icons.includes('tail-in') || e.matches('.message-in') || !!e.closest('.message-in') || !!e.querySelector('.message-in');
  const outgoing = icons.includes('tail-out') || e.matches('.message-out') || !!e.closest('.message-out') || !!e.querySelector('.message-out');
  let direction=incoming&&!outgoing?'entrada':outgoing&&!incoming?'saida':'desconhecida';
  let evidence=direction==='desconhecida'?'nenhuma':'marcador';
  if(!incoming && !outgoing && hasIn && hasOut) {
    const candidates=labels.get(signature(wrapper(e)));
    if(candidates && candidates.size===1) {
      direction=[...candidates][0]; evidence='estrutura_calibrada';
    }
  }
  const structure = [];
  let node = body || e;
  for (let i=0; node && node!==root && i<10; i++,node=node.parentElement) {
    structure.push({tag:node.tagName,classes:node.getAttribute('class')||'',role:node.getAttribute('role')||'',testid:node.getAttribute('data-testid')||'',attributes:[...node.attributes].map(a=>a.name)});
  }
  return {id:e.getAttribute('data-id'), text:body?body.innerText:'', direction,evidence,structure,icons};
}) : [];
return {online:navigator.onLine, list:!!document.querySelector('#pane-side'), name, rows};
'''

def run():
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    if os.getenv('WHATSAPP_ENVIAR', '0') != '0':
        raise SystemExit('Monitor somente leitura: configure WHATSAPP_ENVIAR=0.')
    previa = None
    if os.getenv('WHATSAPP_PREVIA_MOTOR', '0') == '1':
        from .previa_motor import PreviaMotor
        previa = PreviaMotor(os.getenv('WHATSAPP_CONTATOS_TESTE', ''), os.getenv('WHATSAPP_NOME_TESTE', ''))
        print('PREVIA ATIVA: vinculo manual de teste, telefone NAO verificado pelo programa. Banco em memoria; sem IA/alertas/envio.', flush=True)
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
        print('MONITOR SOMENTE LEITURA. Abra a conversa desejada nesta janela.', flush=True)
        print('Nenhuma resposta sera enviada. Sugestoes do motor somente se PREVIA ATIVA.', flush=True)
        print('Apenas conversa aberta e elementos carregados; nao monitora todas as conversas.', flush=True)
        print('Direcao: marcadores ou estrutura calibrada com entrada E saida visiveis. Ambiguidade=desconhecida.', flush=True)
        print('Estrutura calibrada e uma heuristica para previa, nao confirma telefone nem autoriza envio.', flush=True)
        print('Diagnostico automatico: ate 2 estruturas por conversa; sem IDs, telefone ou texto dentro do bloco tecnico.', flush=True)
        active = None
        seen = set()
        previous = None
        diagnostic_count = 0
        diagnostic_seen = set()
        while True:
            state = driver.execute_script(SCRIPT)
            if not state['online'] or not state['list'] or not state['name']:
                if previa and active == previa.nome:
                    previa.pausar()
                active = None
                seen.clear()
                notice = 'Aguardando conexao, login ou conversa aberta; leitura pausada.'
            else:
                name = state['name']
                rows = state['rows']
                ids = {r['id'] for r in rows if r['id']}
                if active != name:
                    if previa and active == previa.nome:
                        previa.pausar()
                    active = name
                    seen = ids
                    diagnostic_count = 0
                    diagnostic_seen = set()
                    notice = 'Observando: ' + name + ' | telefone NAO confirmado | historico inicial ignorado.'
                else:
                    notice = 'Observando: ' + name + ' | telefone NAO confirmado | aguardando novos elementos.'
                    batch = set()
                    fresh = [r for r in rows if r['id'] and r['id'] not in seen]
                    if previa and name == previa.nome and any(r['direction'] == 'saida' for r in fresh):
                        previa.pausar()
                    for row in fresh:
                        ident = row['id']
                        if ident in batch:
                            continue
                        batch.add(ident)
                        text = row['text'].strip()
                        if text:
                            print(time.strftime('%H:%M:%S') + ' | ' + name + ' | ' + row['direction'] + ' | ' + text, flush=True)
                            print('LEITURA | evidencia=' + row['evidence'], flush=True)
                            if previa:
                                previa.processar(name, row['direction'], text)
                            structure = {'ancestrais':row['structure'],'icones':row['icons']}
                            key = json.dumps(structure, sort_keys=True)
                            if row['direction'] == 'desconhecida' and diagnostic_count < 2 and key not in diagnostic_seen:
                                diagnostic_count += 1
                                diagnostic_seen.add(key)
                                print('DIAGNOSTICO_DIRECAO_' + str(diagnostic_count) + '=' + json.dumps(structure, ensure_ascii=True), flush=True)
                    seen.update(ids)
            if notice != previous:
                print(notice, flush=True)
                previous = notice
            time.sleep(2)
    except KeyboardInterrupt:
        print('Monitor parado.', flush=True)
    except Exception as exc:
        print('Monitor interrompido: ' + str(exc), flush=True)
        print('Se Chrome nao iniciou, feche somente a janela antiga do bot antes de reiniciar.', flush=True)
        raise
    finally:
        if previa is not None:
            previa.close()
        if driver is not None:
            try:
                driver.quit()
            except (Exception, KeyboardInterrupt):
                print('Nao foi possivel concluir o fechamento automatico. Feche somente a janela do bot, se ainda estiver aberta.', flush=True)

if __name__ == '__main__':
    run()
