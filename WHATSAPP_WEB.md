# Conector WhatsApp Web / API Python

Implementacao inicial supervisionada, nao homologada em WhatsApp real. Nao substitui o motor nem o diagnostico. Nenhum envio e habilitado pela instalacao.

## Instalar e executar
Na raiz do projeto e no ambiente Python usado pelo servidor:

```powershell
python -m pip install -r requirements.txt selenium
$env:WHATSAPP_API_URL="http://127.0.0.1:8033"
$env:WHATSAPP_ENVIAR="0"
python -m app.atendimento.conector_whatsapp
```

O servidor deve estar rodando separadamente na porta 8033. A chave e lida da configuracao Python existente, nunca escrita neste arquivo. Feche somente o navegador antigo que usa o mesmo perfil antes de iniciar. Conecte pelo QR Code se solicitado.

Previa apenas detecta entradas, sem chamar o motor. Para habilitar envio explicitamente, encerre com Ctrl+C, defina WHATSAPP_ENVIAR=1 e inicie novamente. Somente mensagens posteriores ao inicio sao elegiveis; como o horario exibido nao tem segundos, aguarde o proximo minuto. Mensagens marcadas nao sao repetidas.

## Limites desta entrega
- Sem lista fixa: examina contatos na parte renderizada da lista, inclusive nomes salvos quando o ID confirma um telefone. Nomes duplicados, grupos e IDs somente @lid sao ignorados. Nao resolve telefone por nome.
- Nao garante varredura de conversas fora da lista renderizada, nem recuperacao de todo o historico.
- Agrupa textos novos visiveis da conversa, limitado a 4000 caracteres. Midia nao e processada.
- Encaminha entradas ao servidor mesmo no atendimento humano, preservando o historico; respeita as respostas vazias do motor.
- Assuma pelo painel ANTES de responder manualmente. Intervencao no celular nao e detectada automaticamente. A janela automatizada deve ser exclusiva.
- Respostas humanas escritas no painel ainda NAO sao transportadas por este conector; falta uma fila de saida.
- Estado e contexto sao checados antes do envio, mas a checagem e o Enter nao sao atomicos. Nao usar sem supervisao.
- Falha HTTP, mudanca de contexto ou rascunho encerra a execucao. Mensagem fica marcada antes da API para evitar repeticao ambigua; pode exigir atendimento manual e nao ha garantia de entrega.
- O conector usa os seletores do diagnostico existente. Layout, formatos de data e IDs podem exigir ajustes no PC.
- Sem garantia contra bloqueio de conta. Sem alteracao automatica da IA configurada.

Nenhum teste real de Selenium, login, envio, banco ou API local foi executado no ambiente de desenvolvimento desta entrega.
