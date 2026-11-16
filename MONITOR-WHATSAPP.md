# Monitor local somente leitura

Pare o programa anterior com Ctrl+C. Nao execute duas instancias com o mesmo perfil.

```powershell
$env:WHATSAPP_ENVIAR="0"
python -m app.atendimento.monitor_whatsapp
```

Abra manualmente a conversa desejada na janela criada pelo programa. O monitor le a conversa aberta continuamente, enquanto processo e PC estiverem ativos. Nao se conecta a uma janela arbitraria do Chrome pessoal. Reutiliza whatsapp-perfil. Nao requer Console/F12. Para parar: Ctrl+C.

Nao envia, nao digita, nao clica em conversas, nao chama motor/IA e nao grava transcricoes em arquivo. Exibe textos no terminal local; evite compartilhar esse terminal se houver dados pessoais. Nomes sao rotulos, nao confirmacao de identidade ou telefone.

Ignora IDs presentes ao iniciar/selecionar uma conversa. Mudanca de nome ou perda detectada de lista/rede reinicia a linha de base. Conversas diferentes com mesmo nome podem nao ser distinguidas. Elementos carregados depois podem ser historico ou sincronizacao tardia; uma linha nova no terminal nao comprova mensagem recebida agora. Rolagem pode carregar mensagens antigas. Nao ha garantia de entrega completa, deteccao de toda desconexao ou classificacao correta de direcao. Nao acompanha conversas fechadas nem toda a lista.

Este modulo contorna apenas a necessidade de telefone para observacao humana sem envio; nao resolve a confirmacao de identidade do transporte de respostas. O atendimento automatico continua pendente e nao deve ser ativado por causa deste monitor. Nao validado em WhatsApp real.
