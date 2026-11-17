(function () {
  'use strict';

  const API = '';

  function chave() {
    return localStorage.getItem('assinaturas.apiKey') || 'sessao-local';
  }

  async function api(caminho, opcoes = {}) {
    const resposta = await fetch(API + caminho, {
      ...opcoes,
      headers: {
        'Content-Type': 'application/json',
        'X-API-Key': chave(),
        ...(opcoes.headers || {}),
      },
    });
    if (!resposta.ok) {
      let detalhe = '';
      try {
        const corpo = await resposta.json();
        detalhe = corpo.detail || '';
      } catch (_) {}
      throw new Error(detalhe || 'Erro ' + resposta.status);
    }
    if (resposta.status === 204) return null;
    return resposta.json();
  }

  function aviso(texto, erro = false) {
    const toast = document.createElement('div');
    toast.textContent = texto;
    toast.style.cssText = [
      'position:fixed', 'bottom:24px', 'left:50%', 'transform:translateX(-50%)',
      'background:#232052', 'color:#fff', 'padding:12px 18px', 'border-radius:12px',
      'border:1px solid ' + (erro ? '#ff5c7a' : '#2fcf8f'),
      'z-index:9999', 'font:13px system-ui', 'box-shadow:0 12px 30px rgba(0,0,0,.4)',
    ].join(';');
    document.body.appendChild(toast);
    setTimeout(() => toast.remove(), 3500);
  }

  function modal(titulo, corpoHtml) {
    const fundo = document.createElement('div');
    fundo.style.cssText = 'position:fixed;inset:0;z-index:9998;display:grid;place-items:center;background:rgba(7,5,20,.82);padding:16px';
    fundo.innerHTML = `
      <div style="width:min(480px,94vw);max-height:92vh;overflow:auto;background:#1b1740;color:#eef0ff;border:1px solid #ffffff22;border-radius:16px;padding:22px;font:13px system-ui">
        <h3 style="margin:0 0 12px">${titulo}</h3>
        ${corpoHtml}
      </div>
    `;
    fundo.addEventListener('click', (evento) => {
      if (evento.target === fundo) fundo.remove();
    });
    document.body.appendChild(fundo);
    return fundo;
  }

  function campo(rotulo, input) {
    return `<label style="display:block;margin:12px 0 6px;color:#9aa0c7;font-size:12px">${rotulo}</label>${input}`;
  }

  async function filtrarPlanosAtivos() {
    const select = document.getElementById('novoPlano');
    if (!select) return;
    try {
      const planos = await api('/planos?apenas_ativos=true');
      const valorAtual = select.value;
      select.innerHTML = '<option value="">— sem plano —</option>';
      planos.forEach((plano) => {
        const opcao = document.createElement('option');
        opcao.value = plano.nome;
        opcao.textContent = plano.nome;
        select.appendChild(opcao);
      });
      if (valorAtual && planos.some((plano) => plano.nome === valorAtual)) {
        select.value = valorAtual;
      }
    } catch (_) {
      // nao interrompe o painel se a consulta falhar
    }
  }

  function abrirRecebimento() {
    const hoje = new Date().toISOString().slice(0, 10);
    const caixa = modal('Registrar recebimento', `
      ${campo('ID da assinatura', '<input id="extraRecebimentoId" type="number" min="1" style="width:100%;padding:10px;border-radius:10px;border:1px solid #ffffff30;background:#15102c;color:#fff">')}
      ${campo('Valor (R$)', '<input id="extraRecebimentoValor" type="number" step="0.01" min="0" style="width:100%;padding:10px;border-radius:10px;border:1px solid #ffffff30;background:#15102c;color:#fff">')}
      ${campo('Data', `<input id="extraRecebimentoData" type="date" value="${hoje}" style="width:100%;padding:10px;border-radius:10px;border:1px solid #ffffff30;background:#15102c;color:#fff">`)}
      ${campo('Forma de pagamento', `
        <select id="extraRecebimentoForma" style="width:100%;padding:10px;border-radius:10px;border:1px solid #ffffff30;background:#15102c;color:#fff">
          <option>PIX</option><option>DINHEIRO</option><option>BOLETO</option><option>DEPOSITO</option><option>CARTAO</option>
        </select>`)}
      ${campo('Descricao', '<input id="extraRecebimentoDescricao" style="width:100%;padding:10px;border-radius:10px;border:1px solid #ffffff30;background:#15102c;color:#fff">')}
      <div style="display:flex;justify-content:flex-end;gap:10px;margin-top:18px">
        <button id="extraCancelarRecebimento" style="padding:9px 16px;border-radius:10px;border:1px solid #ffffff30;background:transparent;color:#fff">Cancelar</button>
        <button id="extraSalvarRecebimento" style="padding:9px 16px;border-radius:10px;border:0;background:linear-gradient(135deg,#4f7cff,#8b5cf6);color:#fff">Registrar</button>
      </div>
    `);
    caixa.querySelector('#extraCancelarRecebimento').onclick = () => caixa.remove();
    caixa.querySelector('#extraSalvarRecebimento').onclick = async () => {
      const id = Number(caixa.querySelector('#extraRecebimentoId').value);
      const valor = Number(caixa.querySelector('#extraRecebimentoValor').value);
      const data = caixa.querySelector('#extraRecebimentoData').value;
      const forma = caixa.querySelector('#extraRecebimentoForma').value;
      const descricao = caixa.querySelector('#extraRecebimentoDescricao').value.trim();
      if (!id || !(valor >= 0)) {
        aviso('Informe um ID de assinatura e um valor valido.', true);
        return;
      }
      try {
        await api(`/assinaturas/${id}/pagamentos`, {
          method: 'POST',
          body: JSON.stringify({ valor, data: data || null, forma_pagamento: forma, descricao: descricao || null }),
        });
        caixa.remove();
        aviso('Recebimento registrado com sucesso.');
      } catch (erro) {
        aviso(erro.message, true);
      }
    };
  }

  async function listarProdutos() {
    const corpo = document.querySelector('#extraTabelaProdutos');
    if (!corpo) return;
    corpo.innerHTML = '<tr><td colspan="5">Carregando...</td></tr>';
    try {
      const produtos = await api('/produtos');
      if (!produtos.length) {
        corpo.innerHTML = '<tr><td colspan="5">Nenhum produto cadastrado.</td></tr>';
        return;
      }
      corpo.innerHTML = produtos.map((produto) => `
        <tr>
          <td>${produto.nome}</td>
          <td>${produto.duracao_fixa ? 'Fixo' : 'Flexivel'}</td>
          <td>${produto.dias} dias</td>
          <td>${produto.ativo ? 'Ativo' : 'Inativo'}</td>
          <td>
            <button data-id="${produto.id}" data-acao="alternar" style="padding:5px 9px;border-radius:8px;border:1px solid #ffffff30;background:transparent;color:#fff">${produto.ativo ? 'Desativar' : 'Ativar'}</button>
          </td>
        </tr>
      `).join('');
      corpo.querySelectorAll('button[data-acao="alternar"]').forEach((botao) => {
        botao.onclick = async () => {
          const id = Number(botao.dataset.id);
          const produto = produtos.find((item) => item.id === id);
          try {
            await api(`/produtos/${id}`, {
              method: 'PATCH',
              body: JSON.stringify({ ativo: !produto.ativo }),
            });
            await listarProdutos();
          } catch (erro) {
            aviso(erro.message, true);
          }
        };
      });
    } catch (erro) {
      corpo.innerHTML = `<tr><td colspan="5">${erro.message}</td></tr>`;
    }
  }

  function abrirNovoProduto() {
    const caixa = modal('Novo produto', `
      ${campo('Nome', '<input id="extraProdutoNome" style="width:100%;padding:10px;border-radius:10px;border:1px solid #ffffff30;background:#15102c;color:#fff">')}
      ${campo('Duracao', `
        <select id="extraProdutoDuracao" style="width:100%;padding:10px;border-radius:10px;border:1px solid #ffffff30;background:#15102c;color:#fff">
          <option value="fixa">Fixa</option>
          <option value="flexivel">Flexivel</option>
        </select>`)}
      ${campo('Dias', '<input id="extraProdutoDias" type="number" min="1" max="3650" value="30" style="width:100%;padding:10px;border-radius:10px;border:1px solid #ffffff30;background:#15102c;color:#fff">')}
      <div style="display:flex;justify-content:flex-end;gap:10px;margin-top:18px">
        <button id="extraCancelarProduto" style="padding:9px 16px;border-radius:10px;border:1px solid #ffffff30;background:transparent;color:#fff">Cancelar</button>
        <button id="extraSalvarProduto" style="padding:9px 16px;border-radius:10px;border:0;background:linear-gradient(135deg,#4f7cff,#8b5cf6);color:#fff">Criar</button>
      </div>
    `);
    caixa.querySelector('#extraCancelarProduto').onclick = () => caixa.remove();
    caixa.querySelector('#extraSalvarProduto').onclick = async () => {
      const nome = caixa.querySelector('#extraProdutoNome').value.trim();
      const fixa = caixa.querySelector('#extraProdutoDuracao').value === 'fixa';
      const dias = Number(caixa.querySelector('#extraProdutoDias').value);
      if (!nome || !(dias > 0)) {
        aviso('Informe nome e dias validos.', true);
        return;
      }
      try {
        await api('/produtos', {
          method: 'POST',
          body: JSON.stringify({ nome, duracao_fixa: fixa, dias, ativo: true }),
        });
        caixa.remove();
        await listarProdutos();
        aviso('Produto criado.');
      } catch (erro) {
        aviso(erro.message, true);
      }
    };
  }

  function iniciar() {
    const acoes = document.querySelector('.acoes');
    if (acoes) {
      const botao = document.createElement('button');
      botao.className = 'botao';
      botao.textContent = 'Registrar recebimento';
      botao.onclick = abrirRecebimento;
      acoes.prepend(botao);
    }

    const conteudo = document.getElementById('conteudo');
    if (conteudo) {
      const secao = document.createElement('section');
      secao.className = 'linha';
      secao.innerHTML = `
        <article class="card col-12" style="background:linear-gradient(160deg,#1b1740,#221d52);border:1px solid #ffffff22;border-radius:16px;padding:18px 20px">
          <div style="display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap">
            <div>
              <h2 style="margin:0 0 4px;font-size:14px">Produtos</h2>
              <div style="color:#9aa0c7;font-size:12px">IPTV tem duracao fixa de 30 dias. Internet permite duracao flexivel.</div>
            </div>
            <button id="extraNovoProduto" style="padding:9px 16px;border-radius:10px;border:1px solid #ffffff30;background:rgba(255,255,255,.05);color:#fff">+ Novo produto</button>
          </div>
          <div style="overflow:auto;margin-top:14px">
            <table style="width:100%;border-collapse:collapse;font-size:12.5px;color:#eef0ff">
              <thead>
                <tr style="color:#9aa0c7;text-align:left">
                  <th style="padding:8px 10px;border-bottom:1px solid #ffffff22">Produto</th>
                  <th style="padding:8px 10px;border-bottom:1px solid #ffffff22">Duracao</th>
                  <th style="padding:8px 10px;border-bottom:1px solid #ffffff22">Dias</th>
                  <th style="padding:8px 10px;border-bottom:1px solid #ffffff22">Situacao</th>
                  <th style="padding:8px 10px;border-bottom:1px solid #ffffff22">Acoes</th>
                </tr>
              </thead>
              <tbody id="extraTabelaProdutos"></tbody>
            </table>
          </div>
        </article>
      `;
      conteudo.appendChild(secao);
      secao.querySelector('#extraNovoProduto').onclick = abrirNovoProduto;
      listarProdutos();
    }

    filtrarPlanosAtivos();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', iniciar);
  } else {
    iniciar();
  }
})();
