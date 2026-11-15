# Fila automatica: teste de abertura por nao lidas

Reutiliza SCRIPT/recentes do monitor e PreviaMotor. Nao altera o motor nem ativa envio. Novo ponto de entrada para validar a selecao automatica, restrito a UM contato. Nao e fila geral de atendimento nem integracao com painel.

```powershell
$env:WHATSAPP_ENVIAR="0"
$env:WHATSAPP_CONTATOS_TESTE="55DDDNUMERO"
$env:WHATSAPP_NOME_TESTE="NOME EXATO"
python -m app.atendimento.fila_whatsapp
```

Pare a instancia anterior antes de executar. Na janela criada pelo programa, deixe a conversa de teste visivel na lista, mas nao selecionada. Apos o horario indicado, envie pelo outro celular quero internet. O programa procura aria-label com mensagens nao lidas/unread, exige uma unica linha com o nome e clica nela. Esse clique pode marcar as mensagens como lidas. Dados do telefone continuam sendo vinculo MANUAL de teste, nao identidade verificada automaticamente.

Depois de confirmar o cabecalho, processa apenas elementos com horario original posterior ao inicio. O minuto de inicio e ignorado. Mensagens sem horario, futuras ou com direcao desconhecida nao consultam o motor. Banco do teste em memoria; sem IA, alertas externos ou envio. Respostas saem apenas no terminal. Teste tambem exige validar o seletor de nao lidas no navegador real; ainda nao homologado.

Somente linhas atualmente carregadas. Nao rola a lista, nao descobre arquivadas ou linhas fora do DOM e nao garante captar toda mensagem. Nao abra manualmente o contato antes do disparo, pois a sinalizacao de nao lidas pode desaparecer. Depois de selecionar automaticamente, mantem a leitura desse contato enquanto ele continua localizado na lista. Mudanca externa da conversa apos selecao encerra; saida recente pausa a previa ate reiniciar. Perda detectada da lista/rede encerra; nao detecta toda desconexao possivel.

Indicadores de nao lidas podem incluir mensagens antigas: abrir por esse indicador nao as torna recentes; o filtro de horario continua obrigatorio. Nomes duplicados visiveis bloqueiam a selecao, mas nao garantem detectar homonimos fora da lista carregada. Nao habilitar envio a partir deste teste. Suporte simultaneo a varios contatos, identidade persistente e fila humana real continuam pendentes.
