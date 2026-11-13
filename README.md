# Atendimento IA — ConnectTV

Projeto **independente** do agente de atendimento da ConnectTV. Ele simula o
WhatsApp em uma página web, responde dúvidas, qualifica internet e IPTV,
transfere para um humano e aprende com as respostas do time.

> O canal ainda é o **simulador**. Nenhuma mensagem é enviada ao WhatsApp real.
> A lógica já está pronta para receber um conector oficial depois.

## Como rodar

```powershell
cd "D:\planilhas\ia atendimento"
python -m pip install -r requirements.txt
.\start.ps1
```

Abra **http://127.0.0.1:8010/atendimento** e informe a chave do `.env`
(`API_KEY`). Para usar outra porta: `$env:PORTA=8011; .\start.ps1`.

- Simulador: `http://127.0.0.1:8010/atendimento`
- Documentação da API: `http://127.0.0.1:8010/docs`
- Saúde: `http://127.0.0.1:8010/health`

## O que o agente faz

- **Internet ilimitada + VPN**: R$ 15 no 1º mês e R$ 20 depois, com teste grátis
  de 4h. Exige chip **TIM ou Vivo** e **recarga nos últimos 3 meses**. Somente
  **Android** (não atende iPhone) e envia o link da Play Store.
- **IPTV Completo**: R$ 30 no 1º mês e R$ 35 depois, com todos os streamers.
- **IPTV Básico**: R$ 20 no 1º mês e R$ 30 depois.
- **Qualificação de IPTV**: marca da TV, se é Smart, foto da loja de aplicativos,
  modelo do TV Box e indicação do app (SmartOne, IBO Player, XCIPTV/DreamTV).
- **Transferência**: só quando o cliente quer contratar/ativar, pede atendente,
  reclama/cancela ou precisa mesmo de uma pessoa. Gera resumo e alerta.
- **Dúvida desconhecida**: o agente avisa que vai confirmar, registra na fila de
  **Dúvidas** e continua o atendimento — não joga o cliente direto para o humano.
- **Pausa variável** antes de cada resposta (0,8s a 6s), simulando digitação
  humana para reduzir risco de ban no número real.

## Base de conhecimento e aprendizado

As respostas oficiais ficam em `dados/conhecimento.json` (somente assuntos do
produto). Quando a IA não sabe, a pergunta entra na fila de **Dúvidas** e o
cliente recebe um aviso gentil — a conversa continua com a IA. No botão
**Dúvidas** do simulador o atendente escreve a resposta e pode:

- **Salvar na base**: ensina o agente para as próximas conversas.
- **Enviar ao cliente**: manda a resposta agora na conversa, sem tirar a IA do
  atendimento.

Também é possível adicionar ou remover entradas manualmente no mesmo painel.

A busca é limitada a assuntos do produto (internet, VPN, IPTV, planos, chip,
TV, aplicativos, pagamento, segurança etc.), então a base não interfere em papo
aleatório.

### Importar histórico do WhatsApp

No painel **Dúvidas → Importar histórico do WhatsApp**, envie o `.txt` exportado
de uma conversa (sem mídia). O agente lê as mensagens, separa pares de
pergunta/resposta e mostra uma lista para revisão. Marque apenas as respostas
corretas e clique em **Salvar selecionadas na base**.

Isso não treina o modelo: as respostas viram entradas da base de conhecimento e
passam a ser usadas no atendimento imediatamente.

## IA opcional (respostas livres)

O `.env` já vem com o Gemini pré-configurado. Falta apenas a chave:

1. Crie uma chave gratuita em <https://aistudio.google.com/app/apikey>.
2. No `.env`, preencha `IA_API_KEY=sua-chave`.
3. Reinicie o servidor (`.\start.ps1`).

```env
IA_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai
IA_API_KEY=sua-chave
IA_MODELO=gemini-3.5-flash
```

Sem chave, funciona no modo roteirizado + base de conhecimento. Com chave, a IA
responde em linguagem natural e recebe a base de conhecimento como referência.
O código bloqueia preços fora do catálogo, promessa de iPhone e teste diferente
de 4h.

## Aplicativos de IPTV

O mapa marca/modelo → app fica em `dados/aplicativos.json` (modelo em
`aplicativos.exemplo.json`). Apps: **SmartOne**, **IBO Player**, **XCIPTV** e
**DreamTV**. Sem mapa por aparelho, usa `APP_IPTV_PADRAO`.

## Endpoints principais

| Método | Rota | Descrição |
|---|---|---|
| GET | `/atendimento` | simulador (não exige chave para abrir a página) |
| GET | `/atendimento/config` | nome, IA ativa, link, contadores |
| GET/POST | `/atendimento/conversas` | listar / iniciar conversa |
| GET | `/atendimento/conversas/{id}` | conversa + mensagens |
| POST | `/atendimento/conversas/{id}/mensagens` | cliente envia texto ou foto |
| POST | `/atendimento/conversas/{id}/assumir` | humano assume |
| POST | `/atendimento/conversas/{id}/responder` | humano responde |
| POST | `/atendimento/conversas/{id}/devolver` | devolve para a IA |
| POST | `/atendimento/conversas/{id}/encerrar` | encerra |
| GET | `/atendimento/alertas` | conversas aguardando humano |
| GET | `/atendimento/duvidas` | perguntas que a IA não soube responder |
| POST | `/atendimento/duvidas/{id}/responder` | responde (ensina a base e pode enviar ao cliente) |
| POST | `/atendimento/duvidas/{id}/ignorar` | remove da fila |
| GET/POST | `/atendimento/conhecimento` | listar / adicionar entradas |
| DELETE | `/atendimento/conhecimento/{indice}` | remover entrada |
| POST | `/atendimento/historico/analisar` | extrai pares pergunta/resposta de um `.txt` do WhatsApp |

Todas as rotas `/atendimento/*` (exceto a página) exigem `X-API-Key`.

## Estrutura

```
app/
  main.py            FastAPI, rotas da página e /health
  config.py          .env, pasta de dados e banco
  database.py        SQLite + sessão
  models.py          conversas, mensagens, dúvidas e eventos
  security.py        validação do X-API-Key
  atendimento/
    motor.py         fluxo, qualificação e transferência
    oferta.py        catálogo, preços e textos oficiais
    conhecimento.py  base editável de perguntas e respostas
    aprendizado.py   fila de dúvidas
    historico.py     leitura de históricos .txt do WhatsApp
    ia.py            cliente de IA compatível com OpenAI
    alertas.py       alerta de transferência (painel + webhook)
    aplicativos.py   mapa aparelho -> app de IPTV
    pausas.py        tempo de resposta variável (anti-ban)
    router.py        endpoints do simulador
web/atendimento.html simulador (HTML/CSS/JS em arquivo único)
dados/               banco atendimento.db (gerado) e conhecimento.json
tests/               testes automatizados
start.ps1            sobe a API local
```

## Testes

```powershell
python -m pytest tests -q
```

## Próximo passo para WhatsApp real

Criar um adaptador (Meta Cloud API ou provedor homologado) que:

1. receba a mensagem e chame `motor.processar_mensagem_cliente`;
2. chame `pausas.esperar(texto)` antes de cada envio;
3. envie o alerta de transferência para `ALERTA_WHATSAPP`;
4. use um número aquecido, com limite diário e sem disparos em massa.

> O projeto de gerenciamento de assinaturas continua separado em
> `D:\planilhas` (painel `/painel`, portas e banco próprios).
