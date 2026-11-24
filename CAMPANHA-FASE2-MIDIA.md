# Campanha — Fase 2: envio de mídia (flyer)

> Documento de planejamento. **Nada aqui está implementado.** Serve para você
> aprovar o desenho antes de qualquer linha de código de envio existir.

## 1. Objetivo

Permitir que a campanha de reativação envie **1 imagem (flyer) com legenda** para
um cliente — em vez de só texto — mantendo:

- envio **supervisionado** (só depois de você liberar);
- **opt-out** sempre visível na legenda;
- risco de banimento **menor** que o de um disparo comum.

## 2. Regra de ouro

**Flyer nunca no primeiro contato.** O fluxo é:

```
1º contato   -> texto curto, sem link, sem imagem (como já está hoje)
cliente responde -> aí sim: flyer + legenda
```

Motivo: número desconhecido + imagem + link é o padrão que o WhatsApp usa para
marcar spam. Depois que a pessoa responde, a conversa existe e o risco cai muito.

Se você quiser enviar imagem já no primeiro contato, isso é uma decisão sua e
precisa ficar registrada como `MIDIA_NO_PRIMEIRO_CONTATO = True` — com aviso na
tela e ciente de que é o caminho de maior risco.

## 3. Situação atual

| Item | Estado |
|---|---|
| Botão `wa.me` na prévia e na fila | funciona, **mas só texto** (o esquema `wa.me` não aceita anexo) |
| Regra do pacote | `app/campanha/mensagens.py` diz explicitamente "sem imagem, audio ou arquivo" |
| Ponte do atendimento (`ia atendimento/whatsapp-web/index.cjs`) | envia **só texto** (linha 99: `client.sendMessage(msg.from, answer)`) |
| Dispositivo vinculado da campanha | **não existe** (Fase 2) |
| Trava de envio | `config.ENVIO_REAL_HABILITADO = False` |
| Node.js nesta máquina | **não está no PATH** (pasta `node_modules` existe, runtime não) |
| Pillow (converter imagem) | **não instalado** |

### 3.1 Já preparado (sem envio)

Implementado e testado, **sem nenhum caminho de envio**:

- `app/campanha/config.py`: `MIDIA_HABILITADA = False`, `MIDIA_NO_PRIMEIRO_CONTATO = False`,
  `MIDIA_PASTA = dados/midia`, formatos `jpg/jpeg/png/webp`, limite 2 MB, legenda 1024.
- `app/campanha/midia.py`: catálogo **somente leitura** da pasta aprovada
  (`listar`, `validar`, `resolver` com bloqueio de `../`, `legenda`).
- `app/campanha/mensagens.py`: `LEGENDA_PADRAO` + `legenda_padrao()`, com opt-out garantido.
- `GET /campanha/midias`: lista imagens, tamanho, validação e legenda.
- `GET /campanha/midias/{arquivo}`: abre a imagem para conferência.
- `GET /campanha/config`: expõe `midia_habilitada`, `midia_no_primeiro_contato`, `legenda_flyer`.
- Pasta criada: `D:\planilhas\dados\midia\` (vazia).

Nada disso envia, nada disso importa rede. `POST /campanha/ativar` continua **409**.

## 4. A mídia

Arquivo candidato: `D:\planilhas\flynet.png`

| Medida | Valor | Comentário |
|---|---|---|
| Dimensões | 1199 × 1312 | quase quadrada (0,914), boa no WhatsApp |
| Peso | 2,2 MB | **pesado** para envio em massa |
| Formato | PNG (foto) | PNG é ineficiente para foto — daí o peso |
| Alvo sugerido | JPEG 1080 px, ~250–350 KB | mesma qualidade visual, ~8× menos dados |

Limites do WhatsApp: imagem até 16 MB; **legenda até 1024 caracteres**
(a mensagem padrão tem ~300 — sobra espaço para o "responda SAIR").

Converter exige **Pillow** (`pip install pillow`) ou ferramenta equivalente.
Instalação de dependência só com sua autorização.

## 5. Desenho técnico

### 5.1 Configuração (`app/campanha/config.py`)

```python
# Fase 2 - midia (desligado por padrao)  <- ja criado em app/campanha/config.py
MIDIA_HABILITADA = False                    # so vira True com o conector pronto
MIDIA_NO_PRIMEIRO_CONTATO = False           # regra de ouro do item 2
MIDIA_PASTA = BASE_DIR / "dados" / "midia"  # onde ficam as imagens aprovadas
MIDIA_FORMATOS = ("jpg", "jpeg", "png", "webp")
MIDIA_TAMANHO_MAX_MB = 2                    # recusa acima disso
MIDIA_LIMITE_LEGENDA = 1024                 # limite do WhatsApp
```

Como no resto do pacote, `MIDIA_HABILITADA = False` é constante fixa e **não**
vem do `.env`.

### 5.2 Banco da campanha (`dados/campanha.db`, aditivo)

```sql
-- 1 imagem por alvo, no maximo
ALTER TABLE alvos   ADD COLUMN midia   TEXT NOT NULL DEFAULT '';
ALTER TABLE alvos   ADD COLUMN legenda TEXT NOT NULL DEFAULT '';
-- registro do que realmente saiu
ALTER TABLE envios  ADD COLUMN midia   TEXT NOT NULL DEFAULT '';
ALTER TABLE envios  ADD COLUMN legenda TEXT NOT NULL DEFAULT '';
```

`legenda` guarda o texto **exato** enviado junto da imagem (auditoria e
prova de que o opt-out estava presente).

### 5.3 Conector (fase 2, dispositivo vinculado próprio)

Decisão anterior mantida: **dispositivo novo (LocalAuth próprio)**, não uma rota
na ponte do atendimento 24h. O atendimento não é tocado.

`whatsapp-web.js` 1.34.8 (a mesma versão já usada no projeto) suporta imagem:

```js
const { Client, LocalAuth, MessageMedia } = require('whatsapp-web.js');

const media = MessageMedia.fromFilePath('/caminho/dados/midia/flyer.jpg');
await client.sendMessage(chatId, media, { caption: legenda });   // imagem + legenda
```

Ordem de envio aprovada para a Fase 2:

1. `sendMessage(chatId, texto)` — só na primeira abordagem;
2. quando o cliente responder e autorizar, `sendMessage(chatId, media, { caption })`.

Nunca duas mensagens seguidas sem resposta (evita aparência de disparo).

### 5.4 Exportação (fase 1, funciona hoje)

O `.jsonl` pode ganhar duas chaves novas sem risco algum:

```json
{"id": 1, "cliente": "DEBORA", "telefone": "5511967945096",
 "texto": "...", "midia": "", "legenda": "", "status": "pendente"}
```

Assim, no ensaio manual, você sabe qual imagem anexar em cada conversa.

## 6. Fluxo do ensaio (só depois da sua liberação)

1. Imagem normalizada em `dados/midia/flyer.jpg` (JPG, ≤ 400 KB).
2. Prévia mostra **texto + miniatura** e o botão *Abrir flyer* (só visualização).
3. Você dispara **1 mensagem** para o **número de teste** e olha o resultado.
4. Você dispara **1 flyer** para você mesmo (resposta simulada).
5. Depois 5 contatos reais que **já responderam** — não a lista fria.
6. Só então a rampa 10 → 20 → 30/dia passa a considerar mídia.

## 7. Checklist de autorização (cada item exige seu "ok" explícito)

- [ ] Instalar Pillow (converter o flyer) — ou você converte e me entrega o JPG.
- [ ] Instalar/confirmar Node.js no PATH (o conector é Node).
- [ ] Virar `MIDIA_HABILITADA = True` (edição de código).
- [ ] Virar `ENVIO_REAL_HABILITADO = True` (edição de código).
- [ ] Parear o dispositivo vinculado com `11992501859`.
- [ ] Autorizar o primeiro envio real, para o número de teste.

Enquanto qualquer um desses estiver desmarcado, a campanha continua sem enviar.

## 8. Riscos e mitigação

| Risco | Mitigação |
|---|---|
| Bloqueio/denúncia por imagem em número desconhecido | mídia só após resposta |
| Legenda cortada | validar 1024 caracteres antes de enviar |
| Arquivo pesado / cliente sem dados | JPG ≤ 400 KB |
| Mesma imagem para todos = "cara de spam" | 2–3 variações de flyer, sorteadas; nunca a mesma sequência |
| Envio repetido para o mesmo número | 1 imagem por alvo (regra no banco) |
| Opt-out perdido na legenda | `mensagens.garantir_optout()` aplicado na legenda também |
| Vazamento de mídia para fora da pasta aprovada | caminho resolvido e validado dentro de `dados/midia` |

## 9. Pendências conhecidas

- `node` e `npm` não estão no PATH desta máquina.
- `Pillow` não instalado.
- `dados/campanha.db` ainda não existe (nasce no primeiro "Criar fila").
- `ENVIO_REAL_HABILITADO = False` — trava ativa.
