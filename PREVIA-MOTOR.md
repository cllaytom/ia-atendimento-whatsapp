# Previa do motor no monitor

Sem envio, sem IA, sem alertas externos. Reutiliza motor.py e a base configurada; nao troca por respostas inventadas. Banco SQLite somente em memoria: historico, duvidas e transferencias do teste somem ao encerrar. Nao altera atendimentos reais. O bloqueio de IA e de notificacao vale apenas no processo local iniciado por este comando.

```powershell
$env:WHATSAPP_ENVIAR="0"
$env:WHATSAPP_PREVIA_MOTOR="1"
$env:WHATSAPP_CONTATOS_TESTE="55DDDNUMERO"
$env:WHATSAPP_NOME_TESTE="NOME EXATO"
python -m app.atendimento.monitor_whatsapp
```

Abra a conversa de teste, aguarde Observando, envie pelo outro celular quero internet. Leia PREVIA DO MOTOR - NAO ENVIADA. Responda as perguntas pelo outro celular, sem enviar mensagens pela conta monitorada. Uma saida, troca de conversa ou perda detectada da lista/rede pausa permanentemente a previa ate reiniciar. O monitor segue lendo. Direcao desconhecida nao consulta o motor.

O telefone foi informado pelo operador, nao confirmado pelo programa. O nome apenas restringe a simulacao; homonimos continuam ambiguos. Nao habilita envio. Mantem os limites do monitor: elementos carregados tardiamente podem ser antigos e nao ha garantia de capturar todas as mensagens. Evite rolar o historico. Sugestoes precisam de revisao humana, inclusive precos, promessas de acao e transferencias; nao foram enviadas nem verificadas como atendimento correto.

Pedidos de midia identificados na resposta sao substituidos por verificacao humana apenas simulada. O filtro e conservador e nao garante classificar toda frase. Em aguardando_humano o fluxo do teste para; reinicie para nova conversa de teste. Esta etapa nao implementa autenticacao de destinatario nem atendimento automatico em producao. Nao validada em WhatsApp real.
