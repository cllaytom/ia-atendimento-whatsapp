# WhatsApp Web ligado ao motor existente

Entry point: python -m app.atendimento.whatsapp_local (ou start-whatsapp.ps1). Usa ponte_whatsapp.receber e a base/motor atuais, sem IA conforme bloqueio da ponte. Nao usa Node.js nem o diretorio whatsapp-web da outra branch.

Teste inicial no PowerShell da raiz do projeto:

```powershell
$env:WHATSAPP_ENVIAR="0"
$env:WHATSAPP_CONTATOS_TESTE="55DDDNUMERO"
python -m app.atendimento.whatsapp_local
```

Informe o nome exato do contato na lista. A conversa precisa estar visivel. So um contato autorizado nesta versao supervisionada. Espere o minuto seguinte e envie texto novo. O modo 0 nao chama motor nem envia. Apos validar, parar e definir WHATSAPP_ENVIAR=1 habilita envio somente ao contato autorizado. Reiniciar cria novo marco; mensagens vistas em simulacao nao sao reprocessadas. Para testar envio, mande outra mensagem nova apos o proximo minuto.

Identidade e confirmada pelo ID da mensagem, nunca pelo nome isolado. Grupos e @lid sao bloqueados. Formato de data suportado: [HH:MM, DD/MM/AAAA], fuso do Windows. So ultima mensagem visivel e analisada; mensagens intermediarias podem ser perdidas. Mensagens do minuto de inicio sao ignoradas. Falhas nao sao reenviadas automaticamente. Perda da lista encerra, mas interrupcoes de rede invisiveis ao DOM nao sao detectadas com garantia. Nao e garantia absoluta contra sincronizacao tardia.

Assuma no painel ANTES de responder manualmente. Responder apenas pelo celular nao e uma pausa persistente automatica. Nao toque na janela automatizada durante execucao. A verificacao e o Enter nao sao atomicos; apenas teste supervisionado. Respostas humanas do painel nao sao transportadas. Alertas nao sao enviados proativamente. Duas instancias simultaneas nao sao suportadas.

O Chrome usa o perfil existente. Feche a janela antiga do bot antes de iniciar. Uma mensagem melhor para falha de sessao nao corrige a causa subjacente. Nao apague o perfil. Nenhum processo e encerrado automaticamente.

O tratamento atual da ponte evita pedidos de midia e transfere a conferencia de aplicativos ao humano; uma lista homologada por modelo continua pendente. Esta entrega conecta o transporte, nao modifica esse catalogo. Nao foi validada em Chrome/WhatsApp real. O canal e nao oficial, pode quebrar e pode causar bloqueio de conta. Nao homologado para uso geral ou sem supervisao.
