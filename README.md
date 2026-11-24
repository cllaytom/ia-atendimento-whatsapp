# API de Assinaturas

API REST (FastAPI + SQLite) para um **agente de IA** gerenciar a base de assinaturas
que hoje vive numa planilha Excel: clientes, planos, vencimentos, renovações,
pagamentos, despesas e auditoria.

> Diagnóstico da planilha original e decisões de arquitetura: [`PLANO.md`](PLANO.md).

## Como funciona

```
Agente de IA  ──HTTP/JSON (OpenAPI)──>  FastAPI  ──>  SQLite (dados/assinaturas.db)
                                            │
                                            ├── importa .xlsb/.xlsx
                                            └── exporta .xlsx
```

O Excel deixa de ser o armazenamento (`.xlsb` só permite leitura com segurança) e passa
a ser **entrada e saída**: importa-se a planilha uma vez e exporta-se quando quiser.

## Instalação

```powershell
cd D:\planilhas
python -m pip install -r requirements.txt
copy .env.example .env      # opcional: ajuste API_KEY
```

### Importar / atualizar a planilha

Fonte oficial: `D:\area  nova\planilha clientes\GERENCIAMENTO DE ASSINATURAS IPTV 86.7 - Copia.xlsb`

```powershell
.\atualizar_base.ps1          # reimporta a planilha oficial
# ou manualmente:
python scripts\importar_planilha.py "D:\area  nova\planilha clientes\GERENCIAMENTO DE ASSINATURAS IPTV 86.7 - Copia.xlsb"
```

Opções: `--aba "BASE DE DADOS"`, `--aba-planos "PLANOS E VALORES"`,
`--recalcular-status` (define ATIVO/INATIVO pela data de vencimento em vez de copiar a coluna).

O comando é **idempotente**: rodar de novo atualiza os registros existentes
(chave = ID + nome) em vez de duplicar. Rodar `atualizar_base.ps1` depois de
qualquer edição no Excel mantém o banco alinhado.

### Subir a API

```powershell
.\start.ps1
# ou: python -m uvicorn app.main:app --reload
```

- **Painel visual: http://127.0.0.1:8010/painel**
- API: http://127.0.0.1:8010
- Documentação interativa (Swagger): http://127.0.0.1:8010/docs
- OpenAPI (o que o agente consome): http://127.0.0.1:8010/openapi.json

O painel (`web/painel.html`) é um arquivo único, sem dependências externas. Para
personalizar: `CONFIG` (título, janela de dias, quantidades) no JavaScript e as
cores nas variáveis `:root` do CSS. Ele pede a `X-API-Key` uma vez e guarda no navegador.

O `start.ps1` sobe apenas em `127.0.0.1` (acessível só nesta máquina) e, se o banco
não existir, importa a planilha oficial automaticamente.

## Autenticação

Todas as rotas (exceto `/health`) exigem o header:

```
X-API-Key: <API_KEY>
```

Defina `API_KEY` no `.env` ou no ambiente. O padrão `dev-local-troque-esta-chave`
serve só para desenvolvimento.

## Painel visual

Em **http://127.0.0.1:8010/painel**:

- indicadores (total, em atraso, vencendo, ativas) e financeiro (carteira, recebido, despesas, lucro);
  os cartões de indicadores são clicáveis e abrem a lista já filtrada;
- gráficos de produto, plano, atraso por faixa e vencimentos por mês;
- **+ Novo cliente** — cadastra nome, contato, usuário/senha, plano, valor, desconto e vencimento
  (o plano preenche valor e data automaticamente);
- **lista de clientes** com busca, filtros e ações por linha:
  - **Renovar** — informa dias, valor e forma de pagamento (gera lançamento financeiro);
  - **Editar** — abre os dados do cliente preenchidos (nome, contato, usuário/senha,
    plano, valor, desconto, vencimento, observação) e salva via `PATCH`;
  - **Ativar / Suspender** — alterna o status;
  - **WhatsApp** — abre `wa.me` com mensagem pronta e editável;
  - **Excluir** — cancela a assinatura (soft delete, some da lista padrão).

As mensagens do WhatsApp ficam em `CONFIG.mensagens` no `web/painel.html`:
`padrao` vale para todos; `vencida` e `aVencer` são opcionais. Variáveis:
`{nome}`, `{plano}`, `{vencimento}`, `{valor}`, `{dias}`. Use `*texto*` para negrito
no WhatsApp.

## Atendimento automático (simulador de WhatsApp)

> **Separação:** o agente de atendimento agora é um projeto independente em
> **`D:\planilhas\ia atendimento`**. Esta cópia em `D:\planilhas` fica como
> legado; use a pasta nova para evoluir o atendimento. A API de assinaturas
> continua neste projeto (painel `/painel`).

Em **http://127.0.0.1:8010/atendimento** existe um simulador de WhatsApp com o
agente de atendimento. Ele serve para testar o fluxo comercial inteiro antes de
conectar um canal real.

> **Importante:** por enquanto o canal é o **simulador**. Nenhuma mensagem é
> enviada ao WhatsApp de verdade. A lógica de conversa, qualificação,
> transferência e alerta já está pronta para receber o conector oficial depois.

### O que o agente faz

- Apresenta o menu: internet ilimitada + VPN, IPTV Completo, IPTV Básico e
  atendimento humano.
- **Internet ilimitada + VPN**: R$ 15 no 1º mês e R$ 20 depois, com teste grátis
  de 4h. Qualifica somente com chip **TIM ou Vivo** e **recarga nos últimos 3
  meses**. Deixa claro que é **somente Android** (não atende iPhone) e envia o
  link da Play Store quando `LINK_APP_ANDROID` está configurado.
- **IPTV Completo**: R$ 30 no 1º mês e R$ 35 depois, com todos os streamers.
- **IPTV Básico**: R$ 20 no 1º mês e R$ 30 depois.
- **IPTV — qualificação**: pergunta a marca da TV, se é Smart, pede uma **foto da
  loja de aplicativos** e, se o cliente usar TV Box, pergunta o modelo para
  indicar o aplicativo correto.
- Só transfere para o humano quando o cliente **quer contratar/ativar**, **pede
  atendimento humano**, reclama ou faz uma pergunta fora do catálogo (pagamento,
  suporte técnico etc.). Antes de transferir, tenta responder pela **base de
  conhecimento** e registra a pergunta na fila de **Dúvidas** para o atendente
  ensinar a resposta.
- Ao transferir, grava um **resumo completo** da qualificação, marca a conversa
  como **Aguardando** e dispara o alerta no painel (e no webhook, se configurado).
- Depois da transferência, a IA **para de responder**. O atendente assume, responde
  e pode devolver a conversa para a IA.

### Como testar

1. Suba a API: `.\start.ps1`
2. Abra **http://127.0.0.1:8010/atendimento**
3. Informe a mesma `X-API-Key` do painel.
4. Clique em **+ Nova conversa** e converse como se fosse o cliente.
5. Quando a conversa for transferida, o alerta aparece no topo. Clique em
   **Assumir conversa** e responda como atendente.
6. **Devolver à IA** reinicia o atendimento automático.

### IA opcional

O agente funciona sem nenhuma IA externa: as respostas de preço, elegibilidade e
qualificação são determinísticas (e por isso nunca inventam valores). Para
liberar respostas livres para dúvidas gerais, configure um endpoint compatível
com OpenAI:

```env
IA_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai
IA_API_KEY=sua-chave
IA_MODELO=gemini-2.0-flash
```

Funciona com Gemini, OpenAI, DeepSeek, Groq, Ollama e outros. Mesmo com IA ligada,
o código bloqueia respostas com preços fora do catálogo, promessa de iPhone ou
teste diferente de 4h. Se a IA falhar, o modo roteirizado assume.

### Base de conhecimento e aprendizado

Além das respostas fixas, o agente consulta uma base editável em
`dados/conhecimento.json` (somente assuntos do produto: internet + VPN e IPTV).
Cada entrada tem `pergunta`, `resposta` e, opcionalmente, `termos` para busca.

Quando a pergunta não está nas respostas do sistema nem na base, o agente:

1. transfere a conversa para o humano, como antes;
2. registra a pergunta na fila de **Dúvidas** (tabela `duvidas_atendimento`);
3. mostra a dúvida no botão **Dúvidas** do simulador.

No painel **Dúvidas** o atendente escreve a resposta oficial. Ao marcar
“Salvar na base”, a resposta entra em `dados/conhecimento.json` e passa a ser
usada nas próximas conversas — o agente “aprende” sem retreinar modelo e sem
risco de inventar preço. Também é possível adicionar/remover entradas
manualmente no mesmo diálogo.

A busca só é usada para mensagens que mencionam o produto vendido
(internet, VPN, IPTV, planos, chip, TV, aplicativos, pagamento etc.), então a
base não interfere em assuntos aleatórios. Se uma resposta não fizer sentido,
basta removê-la no painel ou editar o JSON.

### Aplicativo de IPTV por aparelho

Para o agente dizer o nome do aplicativo correto, preencha
`dados/aplicativos.json` (modelo em [`aplicativos.exemplo.json`](aplicativos.exemplo.json)):

```json
{
  "samsung": "SmartOne",
  "lg": "SmartOne",
  "fire tv": "IBO Player",
  "mxq": "XCIPTV"
}
```

Apps usados: **SmartOne**, **IBO Player**, **XCIPTV** e **DreamTV**. Se o cliente
não conseguir instalar o app indicado, o atendente pode sugerir as alternativas.
Se todos os aparelhos usarem o mesmo aplicativo, basta definir
`APP_IPTV_PADRAO=Nome do app` no `.env`. Sem nenhum dos dois, o agente coleta o
modelo e transfere com a informação de que o aplicativo será confirmado pelo
atendente.

### Tempo de resposta variável (anti-ban)

Para o atendimento não parecer um robô disparando mensagens, cada resposta tem
uma pausa aleatória antes do envio:

- pausa base aleatória entre `ATENDIMENTO_PAUSA_MIN` e `ATENDIMENTO_PAUSA_MAX`;
- acréscimo proporcional ao tamanho da mensagem (`..._POR_CARACTERE`);
- variação final de ±25%, limitada por `ATENDIMENTO_PAUSA_TETO`.

No simulador essa pausa já está ativa (1 a ~4s, dependendo do texto). No canal
real de WhatsApp, o adaptador deve chamar `app.atendimento.pausas.esperar(texto)`
antes de cada envio e, de preferência, marcar presença de “digitando” durante a
espera.

```env
ATENDIMENTO_PAUSA_ATIVA=1
ATENDIMENTO_PAUSA_MIN=0.8
ATENDIMENTO_PAUSA_MAX=2.5
ATENDIMENTO_PAUSA_TETO=6.0
ATENDIMENTO_PAUSA_POR_CARACTERE=0.008
```

Além da pausa, para reduzir risco de banimento no número real: use a API oficial
(Meta Cloud API) ou um provedor homologado, aqueça o número antes de campanhas,
evite disparos em massa e mensagens idênticas para muitos contatos, e mantenha
limite diário de envios.

### Alertas de transferência

- No painel: conversa com badge **Aguardando**, barra de alerta e resumo.
- `ALERTA_WEBHOOK_URL`: recebe um JSON com `conversa_id`, `contato`, `motivo`,
  `resumo` e `alerta_whatsapp` (útil para n8n/Zapier/Make).
- `ALERTA_WHATSAPP`: número de destino do alerta. O envio real por WhatsApp será
  ligado junto com o conector do canal; no simulador ele fica registrado no log e
  no painel.

### Configuração do atendimento (`.env`)

| Variável | Uso |
|---|---|
| `NOME_NEGOCIO` | Nome que aparece na saudação. |
| `LINK_APP_ANDROID` | Link da Play Store enviado após a qualificação. |
| `APP_IPTV_PADRAO` | Aplicativo de IPTV usado quando não houver mapa por aparelho. |
| `ALERTA_WHATSAPP` | Número que recebe o alerta de transferência. |
| `ALERTA_WEBHOOK_URL` | Webhook opcional para o alerta em JSON. |
| `IA_BASE_URL` / `IA_API_KEY` / `IA_MODELO` | IA compatível com OpenAI. |
| `IA_TIMEOUT` | Tempo máximo da chamada de IA, em segundos. |
| `ATENDIMENTO_PAUSA_ATIVA` | Liga/desliga a pausa variável antes de responder. |
| `ATENDIMENTO_PAUSA_MIN` / `..._MAX` | Faixa da pausa base, em segundos. |
| `ATENDIMENTO_PAUSA_TETO` | Tempo máximo de uma resposta, em segundos. |
| `ATENDIMENTO_PAUSA_POR_CARACTERE` | Acréscimo de pausa por caractere. |
| `ARQUIVO_APLICATIVOS` | Caminho alternativo do mapa de aplicativos. |
| `ARQUIVO_CONHECIMENTO` | Caminho alternativo da base de conhecimento (`dados/conhecimento.json`). |

### Endpoints do atendimento

| Método | Rota | Descrição |
|---|---|---|
| GET | `/atendimento` | painel/simulador (não exige chave para abrir a página) |
| GET | `/atendimento/config` | nome do negócio, IA ativa, link e alerta |
| GET | `/atendimento/conversas` | lista conversas (`estado`, `q`, `limite`) |
| POST | `/atendimento/conversas` | inicia conversa no simulador |
| GET | `/atendimento/conversas/{id}` | conversa + mensagens |
| POST | `/atendimento/conversas/{id}/mensagens` | cliente envia texto ou foto |
| POST | `/atendimento/conversas/{id}/assumir` | humano assume |
| POST | `/atendimento/conversas/{id}/responder` | humano responde |
| POST | `/atendimento/conversas/{id}/devolver` | devolve para a IA |
| POST | `/atendimento/conversas/{id}/encerrar` | encerra |
| GET | `/atendimento/alertas` | conversas aguardando humano |
| GET | `/atendimento/duvidas` | perguntas que a IA não soube responder (`status=pendente`) |
| POST | `/atendimento/duvidas/{id}/responder` | salva a resposta (e opcionalmente ensina a base) |
| POST | `/atendimento/duvidas/{id}/ignorar` | remove a dúvida da fila |
| GET | `/atendimento/conhecimento` | lista as entradas da base |
| POST | `/atendimento/conhecimento` | adiciona pergunta/resposta à base |
| DELETE | `/atendimento/conhecimento/{indice}` | remove uma entrada da base |

### Próximo passo para WhatsApp real

O núcleo já separa "receber mensagem do cliente" (`processar_mensagem_cliente`) de
"responder como humano" (`responder_humano`). Para produção, falta plugar um
conector de canal (Meta Cloud API oficial ou Evolution/Z-API) que:

1. receba o webhook do WhatsApp e chame `processar_mensagem_cliente`;
2. envie as respostas da IA/humano pelo mesmo canal;
3. envie o alerta de transferência para `ALERTA_WHATSAPP`.

## Endpoints

| Método | Rota | Descrição |
|---|---|---|
| GET | `/health` | status do serviço |
| GET | `/assinaturas` | lista com filtros: `q`, `status`, `produto`, `plano`, `situacao`, `vencendo_em_dias`, `atrasadas`, `limite`, `deslocamento` |
| GET | `/assinaturas/{id}` | detalhe + credenciais |
| POST | `/assinaturas` | cria assinatura (calcula valor final, vencimento e lucro) |
| PATCH | `/assinaturas/{id}` | atualiza campos |
| DELETE | `/assinaturas/{id}` | cancela (soft delete) |
| POST | `/assinaturas/{id}/renovar` | renova por N dias e lança a receita |
| POST | `/assinaturas/{id}/pagamentos` | registra pagamento avulso |
| GET | `/assinaturas/{id}/lancamentos` | histórico financeiro |
| POST | `/assinaturas/{id}/suspender` \| `/reativar` | muda status operacional |
| GET/POST | `/planos` | catálogo de planos |
| GET/PATCH/DELETE | `/planos/{id}` | manutenção do catálogo |
| GET | `/dashboard` | total, ativas, vencidas, MRR, recebido/despesas/lucro do mês, por produto/plano |
| GET | `/vencimentos?dias=7` | quem vence nos próximos N dias |
| GET | `/inadimplentes` | vencidas e em dia (com dias de atraso) |
| GET/POST | `/lancamentos` | receitas e despesas |
| GET | `/eventos` | auditoria de tudo que foi alterado |
| POST | `/admin/importacao/excel` | upload de `.xlsb/.xlsx` e importação |
| GET | `/admin/exportacao/excel` | baixa a base atual em `.xlsx` |

`situacao` aceita: `ativa`, `vencendo`, `vencida`, `vence_hoje`, `inativa`,
`suspensa`, `cancelada`, `sem_vencimento`.

## Exemplos

```powershell
$h = @{ "X-API-Key" = "dev-local-troque-esta-chave" }

# quem vence nos próximos 7 dias
Invoke-RestMethod "http://127.0.0.1:8010/vencimentos?dias=7" -Headers $h | ConvertTo-Json -Depth 5

# criar assinatura
$corpo = @{
  nome = "MARIA SILVA"; contato = "11 99999-0000"; plano_nome = "MENSAL 30"
  forma_pagamento = "PIX"
  credenciais = @(@{ ordem = 1; usuario = "maria"; senha = "1234" })
} | ConvertTo-Json -Depth 5
Invoke-RestMethod "http://127.0.0.1:8010/assinaturas" -Method Post -Headers $h -ContentType "application/json" -Body $corpo

# renovar
Invoke-RestMethod "http://127.0.0.1:8010/assinaturas/1/renovar" -Method Post -Headers $h `
  -ContentType "application/json" -Body '{"dias":30,"valor":30,"forma_pagamento":"PIX"}'
```

## Estrutura

```
app/
  main.py            aplicação FastAPI
  config.py          variáveis de ambiente
  database.py        engine/sessão SQLite
  models.py          Plano, Assinatura, Credencial, Lancamento, Evento,
                     Conversa, MensagemAtendimento
  schemas.py         contratos (Pydantic)
  importer.py        leitura .xlsb/.xlsx -> banco
  exporter.py        banco -> .xlsx
  security.py        X-API-Key
  auditoria.py       log de alterações
  routers/           assinaturas, planos, relatorios, admin
  atendimento/       agente de atendimento
    motor.py         fluxo, qualificação e transferência
    oferta.py        catálogo, preços e textos oficiais
    ia.py            cliente de IA compatível com OpenAI
    alertas.py       alerta de transferência (painel + webhook)
    aplicativos.py   mapa marca/modelo -> app de IPTV
    conhecimento.py  base editável de perguntas e respostas
    aprendizado.py   fila de dúvidas que o agente não soube responder
    pausas.py        tempo de resposta variável (anti-ban)
    router.py        endpoints do simulador
web/painel.html      painel visual (HTML/CSS/JS unico)
web/atendimento.html simulador de WhatsApp (HTML/CSS/JS unico)
aplicativos.exemplo.json  modelo do mapa de apps de IPTV
scripts/             importar / exportar via linha de comando
tests/               testes da API e do atendimento
dados/               banco SQLite (gerado) e conhecimento.json (editável)
start.ps1            sobe a API (local)
atualizar_base.ps1   reimporta a planilha oficial
```

## Testes

```powershell
python -m pytest tests -q
```
