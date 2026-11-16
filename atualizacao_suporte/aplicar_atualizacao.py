# Verifica/aplica atualizacao local; nao inicia servicos nem envia mensagens.
import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
ROOT=Path.cwd()
BUNDLE=Path(__file__).resolve().parent
EXPECTED={
 'app/main.py':'1c887a810e25a4de262c6be2caf1ea0109f88f01',
 'app/atendimento/ponte_whatsapp.py':'72ee069ef0a46527c983182d7fbe5ec0d009b3bf',
 'whatsapp-web/index.cjs':'91d69c3cd42d3da9218bcd589a3d3f00375a4344',
 'whatsapp-web/package.json':'1b1894ebe4b75256a26799f89a9d4be944dd44dc',
}
def git_hash(data): return hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()
def trocar(text,old,new):
 if text.count(old)!=1: raise RuntimeError('Ancora ausente/repetida; nenhum arquivo foi alterado: '+old[:70])
 return text.replace(old,new,1)
def planejar():
 for relative,expected in EXPECTED.items():
  path=ROOT/relative
  if not path.is_file(): raise RuntimeError('Arquivo nao encontrado: '+relative)
  data=path.read_bytes().replace(b'\r\n',b'\n')
  if git_hash(data)!=expected: raise RuntimeError('Versao local diferente da revisada: '+relative+'. Nao sobrescreva; envie somente o erro para revisao.')
 package=json.loads((ROOT/'whatsapp-web/package.json').read_text(encoding='utf-8-sig'))
 if package.get('scripts',{}).get('start')!='node index.cjs': raise RuntimeError('npm start nao usa o index.cjs revisado. Nada alterado.')
 main=(ROOT/'app/main.py').read_text(encoding='utf-8')
 main=trocar(main,'from .atendimento import router_whatsapp, motor, segmentos','from .atendimento import router_whatsapp, motor, segmentos, suporte_v2')
 main=trocar(main,'    Base.metadata.create_all(bind=engine)','    Base.metadata.create_all(bind=engine)\n    suporte_v2.inicializar()')
 main=trocar(main,'app.include_router(segmentos.router)','app.include_router(segmentos.router)\napp.include_router(suporte_v2.router)')
 main=trocar(main,'<script src="/segmentos.js?v=1"></script></body>','<script src="/segmentos.js?v=1"></script><script src="/revisao-suporte.js?v=1"></script></body>')
 main+='\n\n@app.get("/revisao-suporte.js", include_in_schema=False)\ndef revisao_suporte_script():\n    return FileResponse(BASE_DIR / "web" / "revisao-suporte.js", media_type="text/javascript", headers={"Cache-Control": "no-store"})\n'
 bridge=(ROOT/'app/atendimento/ponte_whatsapp.py').read_text(encoding='utf-8')
 bridge=trocar(bridge,'import re\n','import re\nimport logging\nimport time\n')
 bridge=trocar(bridge,'            pausas.esperar("\\n\\n".join(respostas))','            inicio_pausa = time.perf_counter()\n            pausas.esperar("\\n\\n".join(respostas))\n            logging.getLogger("atendimento.tempos").warning("Pausa adicional aplicada=%.3fs (alvo 2s)", time.perf_counter()-inicio_pausa)')
 bridge=trocar(bridge,'r"foto|print|imagem|v[ií]deo|[aá]udio"','r"(?:mand|envi|precis).{0,55}(?:foto|print|imagem|v[ií]deo|[aá]udio)"')
 bridge=trocar(bridge,'Informe por texto a marca e o modelo exatos do aparelho. Um atendente vai conferir os aplicativos compativeis e continuar o atendimento.','Aguarde um momento, nossa equipe está verificando sua solicitação')
 node=(ROOT/'whatsapp-web/index.cjs').read_text(encoding='utf-8')
 node=trocar(node,"  try {\n    const result = await api('/whatsapp/receber'",'''  let typingStopped = false;
  let typingStarted = false;
  let typingTask = Promise.resolve();
  let typingTimer;
  const startedRequest = Date.now();
  const refreshTyping = () => {
    typingTask = typingTask.then(async () => {
      if (!typingStopped && connected) await chat.sendStateTyping();
    }).catch(() => console.warn('Indicador digitando indisponivel; processamento mantido.'));
    return typingTask;
  };
  try {
    const before = await api('/whatsapp/status/' + number);
    if (before.existe === false || before.estado === 'ia') {
      typingStarted = true;
      await refreshTyping();
      typingTimer = setInterval(refreshTyping, 20000);
    }
    const result = await api('/whatsapp/receber' ''')
 node=node.replace("await api('/whatsapp/receber' ,", "await api('/whatsapp/receber',")
 node=trocar(node,"    const answer = result.respostas.filter(x => typeof x === 'string' && x.trim()).join('\\n\\n');", "    let answer = result.respostas.filter(x => typeof x === 'string' && x.trim()).join('\\n\\n');\n    if (answer && result.estado === 'aguardando_humano') answer = 'Aguarde um momento, nossa equipe está verificando sua solicitação';")
 node=trocar(node,"    console.log('Resposta submetida ao WhatsApp; entrega ao aparelho nao confirmada.');","    console.log('Tempo desde consulta de estado ate submissao: ' + ((Date.now()-startedRequest)/1000).toFixed(3) + 's; inclui ponte, processamento e pausa.');\n    console.log('Resposta submetida ao WhatsApp; entrega ao aparelho nao confirmada.');")
 node=trocar(node,'    throw error;\n  }\n}\nclient.on','''    throw error;
  } finally {
    typingStopped = true;
    clearInterval(typingTimer);
    await typingTask;
    if (typingStarted) await chat.clearState().catch(() => {});
  }
}
client.on''')
 changes={'app/main.py':main,'app/atendimento/ponte_whatsapp.py':bridge,'whatsapp-web/index.cjs':node}
 for relative in ['app/atendimento/suporte_regras.py','app/atendimento/suporte_v2.py','web/revisao-suporte.js']:
  if (ROOT/relative).exists(): raise RuntimeError('Novo arquivo ja existe: '+relative+'. Verifique instalacao anterior; nao sobrescrever.')
  changes[relative]=(BUNDLE/'arquivos'/relative).read_text(encoding='utf-8')
 return changes

def validar(changes):
 subprocess.run([sys.executable,'-B',str(BUNDLE/'testar_suporte.py')],check=True)
 with tempfile.TemporaryDirectory() as tmp:
  for relative,text in changes.items():
   if relative.endswith('.py'): compile(text,relative,'exec')
   if relative.endswith(('.js','.cjs')):
    if not shutil.which('node'): raise RuntimeError('Node nao encontrado para validar JavaScript.')
    path=Path(tmp)/Path(relative).name;path.write_text(text,encoding='utf-8')
    subprocess.run(['node','--check',str(path)],check=True)

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--aplicar',action='store_true');args=parser.parse_args()
 try:
  changes=planejar();validar(changes)
  print('Validacao concluida. Arquivos: '+', '.join(changes))
  if not args.aplicar:
   print('Somente verificacao. Para aplicar, pare Python e conector e rode novamente com --aplicar.');return
  if input('Confirma que Python e conector estao PARADOS? Digite APLICAR: ').strip()!='APLICAR':
   print('Cancelado.');return
  backup=ROOT/'backups_atualizacao'/datetime.now().strftime('%Y%m%d_%H%M%S_%f');backup.mkdir(parents=True)
  originals={relative:(ROOT/relative).read_bytes() if (ROOT/relative).exists() else None for relative in changes}
  for relative,data in originals.items():
   if data is not None:
    destination=backup/relative;destination.parent.mkdir(parents=True,exist_ok=True);destination.write_bytes(data)
  try:
   for relative,text in changes.items():
    destination=ROOT/relative;destination.parent.mkdir(parents=True,exist_ok=True);destination.write_text(text,encoding='utf-8',newline='\n')
  except Exception:
   for relative,data in originals.items():
    destination=ROOT/relative
    if data is None: destination.unlink(missing_ok=True)
    else: destination.write_bytes(data)
   raise
  print('Arquivos aplicados. Backup: '+str(backup))
  print('Nenhum servico iniciado e nenhuma mensagem enviada. Teste primeiro com conector parado.')
 except Exception as error:
  print('Atualizacao interrompida: '+str(error));sys.exit(1)
if __name__=='__main__': main()
