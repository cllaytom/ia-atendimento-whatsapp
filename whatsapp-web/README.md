# WhatsApp Web por eventos + servidor Python

Substitui a execucao do conector Selenium; nao execute ambos juntos. Mantem motor, painel e configuracao Python. Nao usa API oficial Meta. Requer Node.js 20 ou superior e o servidor Python na porta 8033.

## Executar no PowerShell

```powershell
cd "D:\planilhas\ia atendimento\whatsapp-web"
node --version
npm install
npm run check
$env:WHATSAPP_API_URL="http://127.0.0.1:8033"
$env:WHATSAPP_ENVIAR="0"
npm start
```

Se PowerShell bloquear npm.ps1, use npm.cmd nos mesmos comandos. API_KEY e lida do .env da raiz ou ambiente; nao compartilhe a chave. A biblioteca usa sessao separada: conecte pelo QR mostrado no terminal ou navegador. Nao publique QR, estado.json ou .wwebjs_auth.

Para envio real, pare com Ctrl+C, defina WHATSAPP_ENVIAR=1 e execute npm start novamente. Isto autoriza respostas para TODAS as conversas individuais elegiveis, sem lista fixa. Previa nao chama o motor. Apenas mensagens de texto recebidas depois do evento CONECTADO sao consideradas. Nao ha recuperacao de mensagens antigas nem retry automatico.

O remetente e obtido do evento, nao do nome ou do DOM. IDs @lid sao resolvidos pelo getContactLidAndPhone da biblioteca; sem telefone confirmado, nao processa. Nao substitui LID por um telefone inventado. Grupos, canais, status e midia ficam fora.

A fila e por identificador remoto, de modo que uma conversa aguardando API nao bloqueia globalmente as outras. Mudanca entre aliases LID/telefone ainda pode exigir serializacao adicional no servidor.

## Humano e falhas
Assuma a conversa PELO PAINEL antes de responder no celular/WhatsApp. Intervencao manual nao e detectada automaticamente. O motor recebe entradas mesmo no modo humano para registrar o historico, mas nao deve gerar respostas. Antes de enviar, consulta novamente o estado. A verificacao e o envio nao sao atomicos.

Esta entrega NAO envia respostas humanas do painel; essa parte ainda requer fila de saida. A conversa nova criada pela ponte pode registrar uma saudacao que nao integra o retorno da primeira mensagem. Alertas adicionais ao dono nao sao enviados por este conector.

Uma falha apos chamar a API deixa o ID marcado para nao duplicar; a conversa fica bloqueada nesta execucao. Confira manualmente a entrega antes de reiniciar. Nao apague estado.json para forcar repeticao. O estado guarda IDs, sem textos ou chaves.

Nao foi executado teste real de Node, Chromium, login, API local ou envio nesta entrega. npm run check verifica somente sintaxe. Dependencias nao oficiais podem quebrar, nao garantem disponibilidade nem ausencia de bloqueio da conta. Nao considere homologado antes de validar no computador.
