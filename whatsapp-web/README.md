# Ponte WhatsApp Web: versao inicial para testes supervisionados

Integracao nao oficial, com risco de bloqueio e quebra por mudancas do WhatsApp. Nao e garantia de disponibilidade. Sem IA/Ollama. Nao foi validada em uma sessao real no desenvolvimento remoto.

## Instalacao no Windows

Requer Python do projeto e Node.js >=22.12. Use duas janelas PowerShell. Nao rode o servidor antigo na mesma porta.

Na raiz do projeto, com dependencias Python instaladas e o .env existente configurado:

```powershell
python -m uvicorn app.whatsapp_web:app --host 127.0.0.1 --port 8010
```

Este entrypoint desativa provedor principal e fallback de IA no processo. Nao modifica as chaves do .env. O painel continua em http://127.0.0.1:8010/atendimento.

Na segunda janela:

```powershell
cd whatsapp-web
npm install
Copy-Item .env.example .env
notepad .env
```

Preencha API_KEY com a mesma chave da API Python. CONTATOS_TESTE deve conter somente numeros autorizados no formato internacional, separados por virgula. Nao coloque o sinal +. Nao publique chaves nem arquivos de sessao.

```powershell
npm start
```

Leia o QR no WhatsApp em Aparelhos conectados. ENVIAR=0 apenas registra elegibilidade; nao responde nem altera conversas. Depois de testar, ENVIAR=1 habilita respostas APENAS aos numeros autorizados. Reinicie a ponte a cada alteracao.

## Somente mensagens novas

Nao consulta historico nem busca nao lidas. Aceita apenas eventos posteriores ao ready, com timestamp estritamente maior que o segundo da conexao. Mensagens no mesmo segundo sao descartadas por seguranca. Reinicios descartam a fila. Desconexao invalida o marco e exige reiniciar a ponte para voltar a atender; nao existe replay. Erros nao geram tentativas automaticas. Duplicatas sao filtradas localmente e na API; falhas podem perder respostas, deliberadamente privilegiando nao duplicar.

Somente texto individual. Grupos, status, midia, mensagens proprias e contatos fora da lista sao ignorados. Identificadores @lid sao ignorados nesta primeira versao, ate haver resolucao de identidade verificada. Alguns contatos podem por isso nao receber respostas.

## Atendimento humano

Assuma a conversa pelo painel ANTES de responder para evitar concorrencia. Mensagens manuais detectadas no WhatsApp pausam localmente o contato. Para retirar uma pausa local, pare a ponte, remova o contato de paused em local-state.json e reinicie; no painel devolva tambem a conversa ao automatico. Ha uma pequena janela inevitavel entre a verificacao e o envio; nao e transacao atomica com o WhatsApp. Respostas digitadas no painel NAO sao enviadas por esta ponte: use o WhatsApp para falar manualmente. Alertas permanecem no painel; nao ha disparo proativo de alerta pelo WhatsApp.

## Aplicativos por modelo

compatibilidade.json comeca vazio: nenhum modelo/compatibilidade foi inventado. Preencha modelos com chaves MARCA MODELO e valores listas de apps realmente conferidos. O cliente deve informar a chave exata, desconsiderando maiusculas e pontuacao. O fluxo que antes pedia midia solicita marca/modelo por texto e lista o cadastro; sem correspondencia, encaminha ao humano. O filtro de termos de midia e conservador e pode encaminhar casos adicionais. A mudanca ocorre no canal WhatsApp, nao reescreve o simulador legado.

## Operacao

PC ligado, internet ativa e ambas as janelas abertas. Nao ha servico Windows, reinicio automatico nem ativacao ao iniciar o PC nesta versao. Ctrl+C encerra. Desvincule o aparelho no celular se precisar revogar a sessao. Nao exponha a porta 8010 para a internet. Esta entrega e codigo inicial, nao homologacao de producao.
