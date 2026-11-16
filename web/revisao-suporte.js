(() => {
'use strict';
const toolbar=document.querySelector('.topo .acoes'); if(!toolbar)return;
const launch=document.createElement('button');launch.textContent='Base e dúvidas — filtros';toolbar.append(launch);
const d=document.createElement('dialog');d.className='larga';
d.innerHTML=`<h3>Base e dúvidas — filtros</h3><p>Classificação automática por termos. Revise casos ambíguos. Esta tela não envia mensagens ao cliente.</p>
<label>Tipo <select data-type><option value="base">Base</option><option value="duvidas">Dúvidas e pendências</option></select></label>
<label>Serviço <select data-service><option value="">Todos</option><option value="internet">Internet/celular</option><option value="iptv">IPTV</option><option value="geral">Geral/ambíguo</option></select></label>
<label>Intenção <select data-intent><option value="">Todas</option><option value="suporte">Suporte</option><option value="informacao">Informação</option><option value="pagamento">Pagamento/renovação</option></select></label>
<label>Situação <select data-state><option value="">Todas</option><option value="ativo">Ativo (base)</option><option value="pendente">Pendente</option><option value="respondida">Respondida</option><option value="ignorada">Ignorada</option></select></label>
<input data-query placeholder="Buscar pergunta ou resposta"><button data-load>Filtrar/atualizar</button>
<p data-status role="status"></p><div data-list style="max-height:50vh;overflow:auto"></div><div class="acoes-dialogo"><button data-close>Fechar</button></div>`;
document.body.append(d); const get=s=>d.querySelector(s);let busy=false;
async function load(){
 if(busy)return;busy=true;get('[data-load]').disabled=true;
 try{
  const params=new URLSearchParams({tipo:get('[data-type]').value,servico:get('[data-service]').value,intencao:get('[data-intent]').value,status:get('[data-state]').value,q:get('[data-query]').value});
  const result=await api('/atendimento/revisao?'+params);const list=get('[data-list]');list.replaceChildren();get('[data-status]').textContent=result.total+' itens';
  for(const item of result.itens){
   const card=document.createElement('fieldset');const title=document.createElement('legend');title.textContent=item.pergunta;card.append(title);
   const meta=document.createElement('p');meta.textContent=[item.servico,item.intencao,item.status,item.origem].join(' | ');card.append(meta);
   const text=document.createElement('p');text.textContent=item.resposta||item.contexto||'';card.append(text);
   if(item.status==='pendente'){
    const answer=document.createElement('textarea');answer.rows=3;answer.maxLength=4000;answer.placeholder='Resposta oficial revisada, sem dados pessoais nem credenciais';card.append(answer);
    const save=document.createElement('button');save.textContent='Revisar e salvar na base';card.append(save);
    save.addEventListener('click',async()=>{
     if(!answer.value.trim())return;
     if(!confirm('Guardar esta resposta geral na base? Não haverá envio ao cliente.'))return;
     save.disabled=true;
     try{
      const path=item.origem==='revisao'?'/atendimento/revisao/'+item.id+'/responder':'/atendimento/duvidas/'+item.id+'/responder';
      const body=item.origem==='revisao'?{resposta:answer.value.trim()}:{resposta:answer.value.trim(),salvar_na_base:true,enviar_ao_cliente:false};
      await api(path,{metodo:'POST',corpo:body});await load();
     }catch(error){get('[data-status]').textContent=error.message;}finally{save.disabled=false;}
    });
   }
   list.append(card);
  }
 }catch(error){get('[data-status]').textContent=error.message;}finally{busy=false;get('[data-load]').disabled=false;}
}
launch.addEventListener('click',()=>{d.showModal();load();});get('[data-load]').addEventListener('click',load);get('[data-close]').addEventListener('click',()=>d.close());
})();
