import importlib.util
from pathlib import Path
ROOT=Path(__file__).resolve().parent
core=ROOT/'arquivos/app/atendimento/suporte_regras.py'
if not core.exists(): core=ROOT/'suporte_regras.py'
spec=importlib.util.spec_from_file_location('regras',core)
r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)
count=0
def check(text,state=None,service='internet',history=(),action='responder',pending=None,contains=None):
 global count
 result=r.avancar(text,state,service,history)
 assert result is not None,(text,result)
 assert result['acao']==action,(text,result)
 if pending: assert result['estado'].get('pendente')==pending,(text,result)
 if contains: assert contains in result['resposta'],(text,result)
 count+=1
 return result['estado']
s=check('minha internet nao esta funcionando',pending='rede')
s=check('4g',s,pending='operadora')
s=check('Vivo',s,pending='dados')
s=check('fiz e nao funcionou',s,pending='aviao')
s=check('fiz e continua igual 4g',s,pending='servidor')
s=check('ja testei todos os servidores',s,pending='atualizacao')
s=check('ja atualizei e continua',s,pending='reinicio')
s=check('reiniciei e nao resolveu',s,action='transferir')
s=check('minha internet nao funciona aparece E',pending='aviao')
s=check('fiz ficou E',s,pending='local')
s=check('mudei de local continua E',s,pending='reinicio')
s=check('reiniciei continua E',s,contains='Quando houver 4G')
s=check('agora aparece 5g',s,pending='operadora')
s=check('internet nao funciona rede H+',pending='aviao')
s=check('internet nao conecta estou sem sinal',pending='aviao')
s=check('nao esta funcionando',service='',contains='celular (VPN) ou no IPTV')
s=check('celular',s,pending='rede')
s=check('ja coloquei no modo aviao, ja reiniciei e ja testei todos os servidores; 4g; Vivo',{'ativo':True,'rede':'4g','operadora':'Vivo'},pending='dados')
assert {'aviao','reinicio','servidor'}.issubset(s['feitos'])
s=check('nao fiz modo aviao ainda, internet sem sinal',pending='aviao')
assert 'aviao' not in s['feitos']
s=check('ok',s,contains='me conte o resultado')
s=check('nao',s,contains='não conseguiu fazer')
s=check('chovendo e minha internet nao funciona',contains='não confirma a causa')
s=check('voltou a funcionar',{'ativo':True,'rede':'4g'},pending='confirmar_navegacao')
s=check('sim',s,contains='navegação confirmada')
assert s['ativo'] is False
s=check('conectou mas sem internet',{'ativo':True,'rede':'4g','operadora':'TIM'},pending='dados')
check('quero falar com humano',action='transferir')
check('erro de autenticacao na vpn',action='transferir')
check('os canais da IPTV nao funciona',service='iptv',action='delegar_iptv')
assert r.avancar('quero contratar internet',None,'internet') is None
count+=1
check('minha Samsung nao conecta',service='internet',pending='rede')
print(str(count)+' verificacoes do nucleo passaram. Sem chamadas de IA ou WhatsApp.')
