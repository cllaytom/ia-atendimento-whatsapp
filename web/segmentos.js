(() => {
'use strict';
const toolbar = document.querySelector('.topo .acoes');
if (!toolbar) return;
const launch = document.createElement('button');
launch.textContent = 'Segmentos e regras';
toolbar.append(launch);
const dialog = document.createElement('dialog');
dialog.className = 'larga';
dialog.innerHTML = `<h3>Segmentos e regras</h3>
<p>Edite o rascunho, teste e publique. Testar nao salva, nao chama a IA e nao envia ao WhatsApp. A publicacao vale nas proximas mensagens.</p>
<p>Protecoes fixas: falhas de conexao tem prioridade sobre vendas; servico ambiguo exige confirmacao; transferencia usa o aviso padrao da equipe. Marcas de aparelhos nao sao termos iniciais.</p>
<div data-editor style="max-height:45vh;overflow:auto"></div>
<p>Variaveis sao definicoes visiveis para padronizar os dados. Criar uma variavel nao coleta seu valor automaticamente nem confirma pagamentos ou outras acoes.</p>
<label>Mensagem para testar<textarea data-text rows="2"></textarea></label>
<label>Contexto anterior<select data-service></select></label>
<label><input type="checkbox" data-support style="width:auto"> A conversa ja estava em suporte</label>
<pre data-result style="white-space:pre-wrap"></pre>
<div class="acoes-dialogo" style="flex-wrap:wrap"><button data-test>Testar rascunho</button><button data-history>Carregar versao anterior</button><button data-publish class="primario">Revisar e publicar</button><button data-close>Fechar</button></div>
<p data-status role="status"></p>`;
document.body.append(dialog);
const find = selector => dialog.querySelector(selector);
let draft, version, busy = false;
const headings = {segmentos:'Servicos', regras:'Regras', variaveis:'Variaveis'};
const fields = {
 segmentos: {id:'Identificador', nome:'Nome', termos:'Termos (um por linha)', ativo:'Ativo'},
 regras: {id:'Identificador', segmento:'Servico (* = qualquer)', intencao:'Intencao', incluir:'Exemplos que acionam (um por linha)', excluir:'Exclusoes (uma por linha)', prioridade:'Prioridade', acao:'Acao', pergunta:'Pergunta permitida', ativo:'Ativa'},
 variaveis: {id:'Identificador', tipo:'Tipo', descricao:'Descricao'}
};
const choices = {intencao:['suporte','contratacao','informacao','instalacao','pagamento'], acao:['transferir','perguntar','continuar'], tipo:['texto','sim_nao'], pergunta:['','Qual mensagem de erro aparece? Descreva por texto.','Qual e a operadora do chip?','O problema acontece desde quando?']};
function render() {
 const root = find('[data-editor]'); root.replaceChildren();
 for (const group of Object.keys(fields)) {
  const section = document.createElement('details'); section.open = true;
  const title = document.createElement('summary'); title.textContent = headings[group]; section.append(title);
  draft[group].forEach((item, index) => {
   const card = document.createElement('fieldset'); card.style.margin = '10px 0';
   for (const [key, label] of Object.entries(fields[group])) {
    const wrapper = document.createElement('label'); wrapper.style.display = 'block'; wrapper.textContent = label + ' ';
    const value = item[key]; let input;
    if (choices[key]) { input = document.createElement('select'); choices[key].forEach(value => { const option = document.createElement('option'); option.value = value; option.textContent = value || '(nenhuma)'; input.append(option); }); input.value = value || ''; }
    else if (Array.isArray(value) || key === 'descricao') { input = document.createElement('textarea'); input.rows = 2; input.value = Array.isArray(value) ? value.join('\n') : value; }
    else { input = document.createElement('input'); input.type = typeof value === 'boolean' ? 'checkbox' : typeof value === 'number' ? 'number' : 'text'; if (input.type === 'checkbox') input.checked = value; else input.value = value ?? ''; }
    input.style.margin = '5px 0';
    input.addEventListener('input', () => { item[key] = Array.isArray(value) ? input.value.split('\n').map(x => x.trim()).filter(Boolean) : typeof value === 'boolean' ? input.checked : typeof value === 'number' ? Number(input.value) : input.value; });
    wrapper.append(input); card.append(wrapper);
   }
   const remove = document.createElement('button'); remove.textContent = 'Remover do rascunho'; remove.addEventListener('click', () => { draft[group].splice(index,1); render(); }); card.append(remove); section.append(card);
  });
  const add = document.createElement('button'); add.textContent = '+ Adicionar'; add.addEventListener('click', () => {
   const templates = {segmentos:{id:'novo_servico',nome:'Novo servico',termos:[],ativo:true},regras:{id:'nova_regra',segmento:'*',intencao:'suporte',incluir:[],excluir:[],prioridade:100,acao:'transferir',pergunta:'',ativo:true},variaveis:{id:'nova_variavel',tipo:'texto',descricao:''}};
   draft[group].push(templates[group]); render();
  }); section.append(add); root.append(section);
 }
 const select = find('[data-service]'); const previous = select.value; select.replaceChildren();
 for (const item of [{id:'',nome:'Sem contexto'},...draft.segmentos]) { const option=document.createElement('option'); option.value=item.id; option.textContent=item.nome; select.append(option); } select.value=previous;
}
async function run(task) {
 if (busy) return; busy=true;
 const buttons=[...dialog.querySelectorAll('button')]; buttons.forEach(b=>b.disabled=true);
 find('[data-status]').textContent='Processando...';
 try { await task(); }
 catch(error) { find('[data-status]').textContent=error.message; }
 finally { busy=false; buttons.forEach(b=>b.disabled=false); }
}
launch.addEventListener('click', async () => {
 launch.disabled=true;
 try { const saved=await api('/atendimento/segmentos'); version=saved.versao; draft=structuredClone(saved.config); render(); find('[data-status]').textContent='Versao publicada: '+version; find('[data-result]').textContent=''; dialog.showModal(); }
 catch(error) { toast(error.message,true); } finally { launch.disabled=false; }
});
find('[data-close]').addEventListener('click',()=>{if(!busy) dialog.close();});
dialog.addEventListener('cancel',event=>{if(busy)event.preventDefault();});
find('[data-test]').addEventListener('click',()=>run(async()=>{
 const result=await api('/atendimento/segmentos/testar',{metodo:'POST',corpo:{texto:find('[data-text]').value,servico:find('[data-service]').value,dados:find('[data-support]').checked?{intencao:'suporte'}:{},config:draft}});
 find('[data-result]').textContent=JSON.stringify(result,null,2); find('[data-status]').textContent='Somente simulacao: nada enviado ou salvo.';
}));
find('[data-publish]').addEventListener('click',()=>run(async()=>{
 if(!confirm('Publicar estas regras para os proximos atendimentos? Revise os testes antes de confirmar.')) {find('[data-status]').textContent='Publicacao cancelada.';return;}
 const result=await api('/atendimento/segmentos/publicar',{metodo:'POST',corpo:{versao:version,config:draft}}); version=result.versao; draft=structuredClone(result.config); render(); find('[data-status]').textContent='Publicado: versao '+version;
}));
find('[data-history]').addEventListener('click',()=>run(async()=>{
 const result=await api('/atendimento/segmentos/historico');
 const wanted=prompt('Versoes disponiveis: '+result.itens.map(x=>x.versao).join(', ')+'. Qual carregar como rascunho?');
 if(wanted===null) {find('[data-status]').textContent='Cancelado.';return;}
 const item=result.itens.find(x=>String(x.versao)===wanted.trim()); if(!item)throw Error('Versao nao encontrada.'); draft=structuredClone(item.config);render(); find('[data-status]').textContent='Versao '+item.versao+' carregada no rascunho. Revise e publique para restaurar.';
}));
})();
