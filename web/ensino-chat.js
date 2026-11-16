(() => {
  'use strict';
  const button = document.createElement('button');
  button.type = 'button';
  button.textContent = 'Ensinar ao bot';
  button.title = 'Guardar uma resposta humana como conhecimento, sem enviar ao cliente';
  const toolbar = document.querySelector('.topo .acoes');
  if (!toolbar) return;
  toolbar.append(button);
  const dialog = document.createElement('dialog');
  dialog.className = 'larga';
  dialog.innerHTML = `<h3>Ensinar ao bot nesta conversa</h3>
    <p>Selecione uma resposta humana e revise o conhecimento geral. Nada sera enviado ao cliente e o estado da conversa nao sera alterado.</p>
    <form>
      <label>Resposta humana de origem<select name="origem" style="width:100%;margin:8px 0;padding:10px" required></select></label>
      <label>Pergunta que esta resposta resolve<textarea name="pergunta" rows="2" maxlength="600" required></textarea></label>
      <label>Resposta oficial para guardar<textarea name="resposta" rows="5" maxlength="4000" required></textarea></label>
      <p>Substitua nomes, telefones, senhas, comprovantes e detalhes particulares por uma orientacao geral. Nao ensine liberacoes, pagamentos ou verificacoes que o bot nao realizou.</p>
      <p>Por seguranca, a busca direta usara a pergunta completa como frase. Reformulacoes dependem da interpretacao da IA.</p>
      <label style="display:flex;gap:8px;margin:14px 0"><input name="revisado" type="checkbox" required style="width:auto;margin:0"> Revisei: esta resposta e geral, nao contem dados particulares e respeita as regras oficiais.</label>
      <p data-status role="status" aria-live="polite"></p>
      <div class="acoes-dialogo"><button type="button" data-close>Cancelar</button><button type="submit" class="primario">Salvar conhecimento</button></div>
    </form>`;
  document.body.append(dialog);
  const form = dialog.querySelector('form');
  const field = name => form.elements.namedItem(name);
  const status = dialog.querySelector('[data-status]');
  let options = [];
  let saving = false;
  const normalize = value => String(value || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().replace(/\s+/g, ' ').trim();
  const valid = text => typeof text === 'string' && text.trim();
  const privateData = text => /(?:\d[\s().+-]*){11,}|[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}|\b(?:senha|password|token|api[_ -]?key)\s*[:=]\s*\S+/i.test(text);
  function fill() {
    const item = options[Number(field('origem').value)];
    if (!item) return;
    field('pergunta').value = item.question;
    field('resposta').value = item.answer;
    field('revisado').checked = false;
    status.textContent = '';
  }
  field('origem').addEventListener('change', fill);
  for (const name of ['pergunta', 'resposta']) field(name).addEventListener('input', () => { field('revisado').checked = false; });
  dialog.querySelector('[data-close]').addEventListener('click', () => { if (!saving) dialog.close(); });
  dialog.addEventListener('cancel', event => { if (saving) event.preventDefault(); });
  button.addEventListener('click', async () => {
    button.disabled = true;
    try {
      const current = ESTADO.atual;
      const id = current && typeof current === 'object' ? (current.conversa?.id ?? current.id) : current;
      if (!Number.isInteger(Number(id)) || Number(id) < 1) throw Error('Abra uma conversa antes de ensinar.');
      const detail = await api('/atendimento/conversas/' + Number(id));
      if (!detail || !Array.isArray(detail.mensagens)) throw Error('Nao foi possivel ler as mensagens.');
      options = [];
      let question = '';
      for (const message of detail.mensagens) {
        if (message.autor === 'cliente' && valid(message.texto)) question = message.texto.trim();
        if (message.autor === 'humano' && valid(message.texto)) options.push({ question, answer: message.texto.trim(), id: message.id });
      }
      if (!options.length) throw Error('Esta conversa ainda nao tem resposta humana registrada no painel.');
      const select = field('origem');
      select.replaceChildren();
      options.forEach((item, index) => {
        const option = document.createElement('option');
        option.value = String(index);
        option.textContent = '#' + item.id + ' - ' + item.answer.slice(0, 100);
        select.append(option);
      });
      select.value = String(options.length - 1);
      fill();
      dialog.showModal();
    } catch (error) { toast(error.message, true); }
    finally { button.disabled = false; }
  });
  form.addEventListener('submit', async event => {
    event.preventDefault();
    if (saving || !form.reportValidity()) return;
    const question = field('pergunta').value.trim();
    const answer = field('resposta').value.trim();
    if (normalize(question).length < 10 || !answer) { status.textContent = 'Escreva uma pergunta especifica de ao menos 10 caracteres e uma resposta.'; return; }
    if (privateData(question + '\n' + answer)) { status.textContent = 'Remova telefones, emails e credenciais antes de guardar conhecimento geral.'; return; }
    saving = true;
    const submit = form.querySelector('[type="submit"]');
    submit.disabled = true;
    status.textContent = 'Verificando a base...';
    try {
      const existing = await api('/atendimento/conhecimento');
      if (!existing || !Array.isArray(existing.itens)) throw Error('Nao foi possivel verificar duplicatas. Nada foi salvo.');
      if (existing.itens.some(item => normalize(item.pergunta) === normalize(question))) throw Error('Essa pergunta ja existe. Revise a entrada em Duvidas > Base de conhecimento; nao foi sobrescrita.');
      status.textContent = 'Salvando...';
      await api('/atendimento/conhecimento', { metodo: 'POST', corpo: { pergunta: question, resposta: answer, termos: [question] } });
      status.textContent = 'Conhecimento salvo. Conversa mantida no estado atual.';
      toast('Conhecimento salvo na base. Nenhuma mensagem enviada ao cliente.');
      dialog.close();
    } catch (error) { status.textContent = error.message + ' Se houve falha de rede, confira a base antes de repetir.'; }
    finally { saving = false; submit.disabled = false; }
  });
})();
