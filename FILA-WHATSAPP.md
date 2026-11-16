# Fila automatica: teste de abertura por nao lidas

Windows/PowerShell interativo. Reutiliza SCRIPT/recentes e PreviaMotor, restrito a UM contato. Sem envio, IA ou alertas; nao integra fila humana real.

```powershell
$env:WHATSAPP_ENVIAR="0"
$env:WHATSAPP_CONTATOS_TESTE="55DDDNUMERO"
$env:WHATSAPP_NOME_TESTE="NOME EXATO"
python -m app.atendimento.fila_whatsapp
```

Pare a instancia anterior. Deixe o contato visivel na lista, nao selecionado. Apos o horario indicado, envie mensagem pelo outro celular. O programa seleciona a unica linha carregada com nome exato e indicador de nao lidas; isso pode marcar mensagens como lidas. Telefone informado manualmente, nao verificado automaticamente.

Depois da selecao automatica, trocar de conversa ou detectar cabecalho diferente pausa a fila sem fechar o navegador. Enquanto pausada nao consulta conversas nem clica. No terminal em foco, P pausa e R retoma, sem Enter. R autoriza reabrir o contato mesmo sem indicador de nao lidas, preserva o estado do motor em memoria e cria novo marco temporal. Mensagens do intervalo pausado e do minuto de retomada sao ignoradas. Aguarde o novo horario indicado antes de enviar outro teste. R nao devolve automaticamente ao bot uma conversa que chegou a aguardando_humano; nesse caso reinicie o teste. Ctrl+C encerra e tenta fechar a janela.

Saida recente tambem pausa, sem processar entradas do mesmo lote. Falta de confirmacao apos clique pausa. Perda detectada de lista/rede ainda encerra e exige reinicio. A verificacao de troca e por polling, nao atomica: nao detecta necessariamente troca e retorno entre leituras. Antes da primeira selecao automatica, use P se precisar controlar a janela sem cliques do programa. Apos R, nao mexa ate confirmar abertura.

So linhas carregadas: nao rola lista nem encontra arquivadas/fora do DOM. Nomes duplicados visiveis bloqueiam, mas nao excluem homonimos fora da lista. Horario original obrigatorio e posterior ao marco; sem horario, futuro ou direcao desconhecida nao consulta motor. Estrutura calibrada e heuristica de previa, nao autorizacao de envio. Nao ha garantia de capturar todas as mensagens. Estado do teste apenas em memoria. Suporte a varios contatos e painel persistente continuam pendentes. Nao validado em navegador real.
