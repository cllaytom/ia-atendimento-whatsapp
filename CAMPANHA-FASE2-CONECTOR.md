# Campanha — Fase 2: integração com WhatsApp Web

> Estado: **cérebro pronto e testado; envio real ainda desligado.**
> `config.ENVIO_REAL_HABILITADO = False` continua sendo a trava.

## 1. Princípio: cérebro no Python, braço no Node

```
app/campanha/conector.py        decide: pode falar? quem? quanto esperar?
        ▲  HTTP + X-API-Key
campanha-whatsapp/worker.cjs    obedece: pega 1 alvo, digita, envia, confirma
        ▼
WhatsApp Web (dispositivo vinculado próprio)
```

Toda regra que protege o número mora no Python (que tem testes). O worker não
decide nada: se ele travar, cair a internet ou você fechar a janela, nada
dispara em rajada.

## 2. Endpoints

| Método | Rota | Para que serve |
|---|---|---|
| GET | `/campanha/conector/estado` | liberado? motivo? cota do dia, pendentes, reservados, espera |
| POST | `/campanha/conector/proximo` | **reserva** 1 alvo (`status = enviando`) e devolve texto + tempo de digitação |
| POST | `/campanha/conector/confirmar` | grava `enviado` / `falha` e devolve o intervalo sorteado |
| POST | `/campanha/conector/devolver` | desfaz a reserva sem gravar envio (simulação, Ctrl+C) |
| GET | `/campanha/parametros` | valores atuais, padrões e limites de cada parâmetro |
| POST | `/campanha/parametros` | salva cota, intervalo, pausa, cooldown, tentativas e o toggle de janelas |
| DELETE | `/campanha/parametros` | restaura todos os parâmetros para o padrão |
| POST | `/campanha/conector/erro` | erro fatal do worker (desconexão/auth): registra e **pausa na hora** |
| POST | `/campanha/conector/pulso` | worker avisa que está vivo e em qual modo (`auto`/`manual`) |
| POST | `/campanha/conector/manual/proximo` | reserva o próximo **pedido** feito no painel (modo manual) |
| POST | `/campanha/fila/{id}/enviar` | painel pede o envio manual daquele contato |
| DELETE | `/campanha/fila/{id}/enviar` | cancela o pedido manual ainda não atendido |
| POST | `/campanha/planilha` | lê um `.xlsx/.xlsb/.csv` e devolve as linhas (não grava) |
| POST | `/campanha/numeros/previa` | confere a lista (entra / fica fora) sem gravar |
| POST | `/campanha/numeros` | grava a lista na fila (sem enviar) |
| POST | `/campanha/contatos` | worker envia a lista de contatos do WhatsApp |
| GET | `/campanha/contatos` | lista recebida do WhatsApp (total + linhas) |
| POST | `/campanha/contatos/pedir` | pede ao worker conectado que leia a agenda |
| GET | `/campanha/worker` | estado do robô: online, modo, PID, número conectado |
| POST | `/campanha/worker/ligar` | sobe o robô em segundo plano (`manual`, `enviar` ou `parear`) |
| POST | `/campanha/worker/desligar` | pede o encerramento; `{"forcar": true}` mata o processo |
| POST | `/campanha/worker/desconectar` | desvincula o número atual (logout de verdade) |
| POST | `/campanha/conector/numero` | worker informa o número pareado |
| GET | `/campanha/saude` | status, falhas seguidas, último erro, erros do worker e falhas recentes |
| GET | `/campanha/logs` | últimas linhas de `dados/campanha-worker.log` |

Enquanto a trava existir, `proximo` responde **409** com
`{"motivo": "...", "esperar_segundos": 0}`.

## 3. Guardas (todas no Python)

- trava `ENVIO_REAL_HABILITADO` **e** `CAMPANHA_MODO=real` **e** campanha ativa
- **modo manual (padrão)**: envia a qualquer hora e dia; as janelas seg–sex
  09:00–11:30 / 14:00–17:30 só valem se o toggle "respeitar janelas" estiver
  marcado no painel (ou `CAMPANHA_JANELAS=1` no ambiente)
- rampa 10 → 20 → 30 por dia (conta dias anteriores que tiveram envio), ou cota
  fixa definida no painel
- intervalo 90–240 s entre envios; pausa longa (10–20 min) a cada 10
- 1 tentativa por número (`MAX_TENTATIVAS = 1`), ajustável de 1 a 5 no painel
- opt-out, cooldown de 60 dias e o próprio remetente saem da fila na hora
- reserva válida por 15 min; se o worker morrer, o alvo volta sozinho
- `/ativar` no modo real exige `{"confirmo": "ENVIAR"}`

## 3.1 Parâmetros de envio no painel

O card **Parâmetros de envio** (abaixo de "Números da campanha") edita, sem
reiniciar o worker, com persistência em `dados/campanha.db` (chave `parametros`
da tabela `estado`):

| Parâmetro | Padrão | Faixa | Efeito |
|---|---|---|---|
| Cota diária | 0 | 0–100 | 0 = rampa 10/20/30; outro valor = cota fixa |
| Intervalo mín/máx | 90/240 s | 10–3600 s | espera sorteada entre envios |
| Pausa longa a cada | 10 | 1–100 | envios entre pausas longas |
| Pausa mín/máx | 600/1200 s | 30–7200 s | duração sorteada da pausa |
| Cooldown | 60 dias | 0–365 | tempo antes de repetir o mesmo número |
| Tentativas | 1 | 1–5 | 1 = falha definitiva; 2+ devolve o alvo à fila |
| Falhas seguidas até pausar | 3 | 0–20 | 0 = nunca pausa; N = pausa automática após N falhas |
| Respeitar janelas | desmarcado | — | marcado = seg–sex 09:00–11:30 / 14:00–17:30 |

O servidor valida faixas e coerência (`mín <= máx`); valores inválidos voltam
**422**. `DELETE /campanha/parametros` restaura os padrões do `config.py`.
Nada disso envia mensagem: só muda as regras aplicadas na próxima reserva.

## 3.2 Pausa automática e saúde do envio

Duas travas novas impedem o worker de insistir em enviar com erro:

1. **Falhas consecutivas de envio** (ack 0, exceção, número inválido): cada
   `falha` incrementa `falhas_consecutivas`; um `enviado` zera. Ao atingir
   `max_falhas_seguidas` (padrão **3**), a campanha é desligada com motivo
   `pausa automatica: N falhas seguidas de envio - <erro>`. Reativar no painel
   zera o contador.
2. **Erro fatal do worker** (WhatsApp desconectado ou falha de autenticação):
   o worker chama `POST /campanha/conector/erro` e a campanha pausa **na hora**,
   sem esperar as 3 falhas. Ao encerrar por Ctrl+C o worker não reporta erro
   (destroy do Chrome não conta como desconexão).

O painel mostra o cartão **Saúde do envio**: status (`OK`, `ATENÇÃO`,
`PAUSADA`, `DESLIGADA`), falhas seguidas, último erro de envio, erros do worker,
as 5 falhas mais recentes e o log. O worker grava
`dados/campanha-worker.log` (rotaciona em 2 MB para `.1`); a API lê as últimas
linhas em `GET /campanha/logs`. Nenhum desses endpoints envia mensagem.

Números inexistentes no WhatsApp (`numero sem WhatsApp`) **não** entram nessa
contagem: são marcados como `falha` individual e o worker segue para o próximo.
Assim um lote com vários números antigos não desliga a campanha à toa.

## 3.3 Modo manual (atendente no controle)

Além do envio automático (`--enviar`), o worker tem o modo **manual**:

```powershell
.\campanha-whatsapp\start.ps1 --manual
```

Nesse modo ele conecta no WhatsApp e **não envia nada sozinho**. O painel mostra
`worker manual online` e libera o botão **Enviar agora** em cada contato
`pendente` da fila:

1. o botão grava um **pedido** (`POST /campanha/fila/{id}/enviar`);
2. o worker consulta `/campanha/conector/manual/proximo` a cada 2 s;
3. ao achar o pedido, reserva o alvo, digita e envia (sem intervalo, sem pausa
   longa);
4. confirma o resultado e o painel mostra `enviado` ou `falha`.

Regras do manual:

- **não** usa cota diária, janela de horário nem intervalo;
- continua exigindo trava liberada, `CAMPANHA_MODO=real` e campanha **ativa**;
- opt-out, cooldown e o próprio remetente continuam bloqueados;
- se o worker cair no meio, o pedido fica aberto e o alvo volta para a fila
  após 15 min (o botão pode ser clicado de novo).

O botão só funciona com um worker em modo manual conectado (o servidor responde
**409** caso contrário). Pedidos também podem ser cancelados pelo painel.

## 3.4 Importar números (planilha, lista ou WhatsApp)

O cartão **Adicionar números** aceita três origens, sempre com conferência
antes de gravar:

1. **Planilha** `.xlsx`, `.xlsm`, `.xlsb`, `.csv`, `.txt` ou `.tsv`
   (`POST /campanha/planilha`). O cabeçalho é reconhecido sozinho
   (`telefone/celular/whatsapp`, `nome/cliente`, `produto/plano`,
   `vencimento`). Sem cabeçalho, a ordem é telefone, nome, produto,
   vencimento. Datas `31/12/2026` e datas do Excel viram `2026-12-31`.
   O arquivo não é gravado em disco: é lido na memória e devolvido como lista.
2. **Lista colada** do Excel: uma linha por contato, separando por `;`, tab
   ou vírgula (`11999998888;Nome;Produto;31/12/2026`).
3. **Contatos do WhatsApp** (`POST /campanha/contatos/pedir`): o worker
   conectado lê a agenda (`getContacts`) no próximo pulso e envia em lotes de
   500. Grupos, listas de transmissão, o próprio remetente, o número de teste
   e números inválidos são descartados. A lista só preenche a conferência.

Antes de gravar, `POST /campanha/numeros/previa` mostra quantos entram e o
motivo de cada descarte; `POST /campanha/numeros` grava. Guardas aplicadas:

- número precisa ser `55 + DDD + 9 + 8 dígitos` (13 dígitos): os de 12 dígitos
  ficam de fora com o aviso do 9º dígito;
- opt-out, cooldown, remetente, número de teste e quem já está na fila ficam
  de fora;
- quem já passou pela campanha (`falha`/`enviado`) também não volta — uma
  reimportação não repete contato;
- a mensagem vem do cartão **Filtro e mensagem** e recebe `{nome}` e a linha
  `SAIR` como no resto da campanha.

Nada disso envia mensagem: os números entram como `pendente` para o
**Enviar agora** (manual) ou o envio automático.

A lista de contatos do WhatsApp fica guardada em `contatos_whatsapp` e é
**atualizada a cada pedido** (mesmo telefone é sobrescrito com o nome mais
recente). Números que saírem da agenda **não** são apagados automaticamente:
a tabela funciona como base de consulta para importações futuras. Ela não entra
na fila sozinha nem é usada como público da campanha sem passar pela conferência.

## 3.5 Robô pelo painel e troca de número

O painel abre e fecha o robô sem terminal (`start.cmd` continua valendo como
alternativa):

- **Ligar robô (manual)** — `POST /campanha/worker/ligar {"modo":"manual"}`.
  Sobe o `worker.cjs` destacado, com o perfil exclusivo do Chrome. Nada é
  enviado: ele só atende o botão **Enviar agora**.
- **Ligar automático** — mesmo endpoint com `"modo":"enviar"` **e**
  `"confirmo":"ENVIAR"`; sem a confirmação o servidor responde 409.
- **Desligar robô** — pede o encerramento pelo pulso; se ele não responder em
  ~18 s, o painel força (`{"forcar":true}`). O WhatsApp continua pareado.
- **Ligar sozinho ao abrir o painel** — opção no cartão do robô (padrão ligada),
  sempre em modo manual. Clicar em **Desligar robô** desliga essa opção.
- **Trocar número do WhatsApp** — desvincula o número atual
  (`POST /campanha/worker/desconectar`, logout de verdade: o aparelho sai da
  lista no celular) e abre o Chrome com o QR (`{"modo":"parear"}`). Depois de
  escanear, o worker informa o número novo em `POST /campanha/conector/numero`
  e o painel avisa se ele difere do remetente da campanha — aí é só ajustar em
  **Mostrar tudo › Números da campanha**.

Só existe **um robô por vez**: o perfil `dados/campanha-sessao/session` não
aceita dois processos. Se já houver um online, o endpoint devolve
`{"ligado": false, "motivo": "..."}` em vez de tentar abrir outro.

A tela tem dois níveis: **simples** (padrão: robô, fila e adicionar contatos) e
**Mostrar tudo** (parâmetros, filtro/mensagem, saúde/logs, opt-out, números
compartilhados). A escolha fica no navegador (`localStorage`).

## 4. Worker

`campanha-whatsapp/worker.cjs` — Node + `whatsapp-web.js` 1.34.8 (só carrega
a biblioteca nos modos `--parear`, `--teste`, `--enviar` e `--manual`; a
simulação roda sem ela).

```powershell
# atalho que encontra o Node sozinho (fnm) e repassa os argumentos
.\campanha-whatsapp\start.ps1              # simulacao
.\campanha-whatsapp\start.ps1 --uma-vez
.\campanha-whatsapp\start.ps1 --perfil     # conferir o perfil exclusivo do Chrome
.\campanha-whatsapp\start.ps1 --parear     # vincular aparelho (QR)
.\campanha-whatsapp\start.ps1 --estado     # ver modo, trava, cota e fila
.\campanha-whatsapp\start.ps1 --numero-teste "11942432179"
.\campanha-whatsapp\start.ps1 --teste      # 1 mensagem para o numero de teste
.\campanha-whatsapp\start.ps1 --enviar     # envio real (exige campanha ativa)
.\campanha-whatsapp\start.ps1 --manual     # espera o botao Enviar agora do painel

# equivalente sem PowerShell (funciona mesmo com ExecutionPolicy bloqueada)
campanha-whatsapp\start.cmd              # simulacao
campanha-whatsapp\start.cmd --manual
campanha-whatsapp\start.cmd --enviar
campanha-whatsapp\start.cmd --parear
campanha-whatsapp\start.cmd --ajuda

# equivalente, com o node no PATH
node campanha-whatsapp\worker.cjs
node campanha-whatsapp\worker.cjs --uma-vez
node campanha-whatsapp\worker.cjs --perfil
node campanha-whatsapp\worker.cjs --parear
node campanha-whatsapp\worker.cjs --estado
node campanha-whatsapp\worker.cjs --numero-teste "11942432179"
node campanha-whatsapp\worker.cjs --teste
node campanha-whatsapp\worker.cjs --enviar
node campanha-whatsapp\worker.cjs --manual
```

Chave da API: variável `CAMPANHA_API_KEY`, argumento `--chave` ou, por último,
a linha `API_KEY` do `.env` da raiz (nunca é exibida).

### Travas do próprio worker

- `--enviar` **nem abre o WhatsApp** se `/conector/estado` disser `trava: true`
  (voltar `ENVIO_REAL_HABILITADO` para `False` restaura esse bloqueio) ou se o
  modo não for `real`. Sai com código 6.
- `--teste` tem as mesmas travas e manda **uma** mensagem para o número de
  teste; a fila não é tocada e nenhum cliente recebe nada.
- `--enviar` sem sessão pareada orienta a rodar `--parear` antes.
- Número sem WhatsApp (`getNumberId` nulo) vira `falha` sem enviar nada.
- **Envio pelo JID do telefone (`telefone@c.us`)**, nunca pelo `@lid` que o
  `getNumberId` devolve hoje. Em 16/11/2026 o envio para `@lid` ficou em
  `ack=0` (nunca saiu) e o mesmo destino via `@c.us` foi entregue. O worker usa
  `waitUntilMsgSent` e só confirma `enviado` com `ack >= 1`; se ficar em 0,
  marca `falha` com "servidor nao confirmou o envio (ack 0)".
- Ctrl+C devolve o alvo reservado para a fila e fecha o navegador.
- **Perfil do Chrome exclusivo** em `dados/campanha-sessao/session`. O worker
  passa esse `userDataDir` explicitamente e recusa iniciar se o caminho cair no
  perfil padrão do Chrome ou no `.wwebjs_auth` do atendimento. Assim o Chrome
  que já está aberto com o perfil padrão (outro robô) não é reaproveitado nem
  fechado. Para conferir sem abrir nada: `--perfil`.
- A sessão fica em `dados/campanha-sessao/` (LocalAuth próprio), longe do
  atendimento 24h.
- Usa o **navegador já instalado** (Chrome, Brave ou Edge) em vez de baixar o
  Chromium do Puppeteer. Para forçar outro caminho:
  `$env:CAMPANHA_CHROME = "C:\...\chrome.exe"`. Firefox não serve.

## 5. Ensaio ponta a ponta já realizado

Servidor descartável em `127.0.0.1:8012`, base falsa de 3 clientes, trava
liberada **só naquele processo**, janela forçada:

```
[20:49:37] --- alvo #1 (validade 15 min) ---
[20:49:37] telefone : +5511999990001
[20:49:37] cliente  : DEBORA TESTE
[20:49:37] digitacao: 14.69s
[20:49:37] mensagem :
   | Olá, Debora! Tudo bem?
   | ...
   | Se preferir não receber mensagens, responda SAIR.
[20:49:37] SIMULACAO: nada foi enviado; alvo devolvido para a fila.
```

Depois do ciclo: `pendentes: 3 | reservados: 0 | enviados_hoje: 0`.
Nada foi enviado, nada foi marcado como enviado, a fila não diminuiu.

## 6. Sequência para ligar (cada item exige seu "ok")

- [x] Revisar o texto final (o ensaio manual de 5 continua valendo como bússola).
- [x] Criar `campanha-whatsapp/package.json` e instalar `whatsapp-web.js` 1.34.8.
- [x] Implementar o trecho de envio no worker (`--enviar`).
- [x] Implementar `--teste` (1 mensagem para o número de teste, fora da fila).
- [x] Parear o dispositivo com `11992501859` (sessão ativa em 16/11/2026).
- [x] `CAMPANHA_MODO=real` + `ENVIO_REAL_HABILITADO = True` (16/11/2026).
- [x] Primeiro envio **para o número de teste** (`--teste` → `11942432179`,
  22:03 de 16/11/2026), com a fila intacta.
- [x] Confirmar recebimento no aparelho de teste (chegou às 22:13, depois da
  correção LID → `@c.us`, com ack 1 no envio e ack 3 no controle para o próprio
  número).
- [ ] `POST /campanha/ativar` com `{"confirmo": "ENVIAR"}`.
- [ ] Depois 5 contatos que já responderam. Só então a rampa 10 → 20 → 30.

Parar tudo leva 1 clique (**Pausar**) ou `POST /campanha/pausar`: o worker
consulta o estado a cada 5 s e para entre mensagens.

## 7. Limites conhecidos

- **Respostas não são lidas**: quem responder "SAIR" não é bloqueado
  automaticamente. Com 1 tentativa por número, ninguém recebe duas mensagens,
  mas o opt-out precisa ser marcado por você na tela.
- Sessão e perfil do Chrome separados do atendimento 24h:
  `dados/campanha-sessao/session` (LocalAuth próprio). O perfil padrão do Chrome
  e o projeto `ia atendimento` não são tocados.
- WhatsApp Web não é API oficial: existe risco de bloqueio, mitigado pela
  rampa, janelas, intervalo e texto sem link.

## 8. Pendências de ambiente

- `node` está instalado via **fnm** (v26.13.1) e não aparece no PATH por padrão.
  O atalho `campanha-whatsapp\start.ps1` acha o executável sozinho; se preferir
  usar `node` direto: `fnm env --use-on-cd | Out-String | Invoke-Expression`.
- Dependências instaladas em `campanha-whatsapp/node_modules` (195 pacotes).
  O Chromium do Puppeteer **não** foi baixado: o worker usa o Chrome instalado.
- Pilha validada: QR gerado em 8,7 s numa sessão temporária (nada vinculado).
- Porta **8011** tem uma instância antiga do app rodando desde 13/11 (sem o menu
  Campanha). Não foi tocada. A API atual está na **8010**.
