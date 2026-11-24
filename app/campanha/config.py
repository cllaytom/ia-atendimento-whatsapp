"""Configuracao da campanha de reativacao.

Nada aqui e enviado automaticamente. A campanha nasce DESLIGADA e so roda
quando alguem chama POST /campanha/ativar e inicia o worker. Desde o
pareamento (16/11/2026) o modo padrao e "real" e a trava esta liberada; para
voltar ao estado seguro, use CAMPANHA_MODO=previa e ENVIO_REAL_HABILITADO =
False.
"""

from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]

# Banco de assinaturas: aberto SOMENTE para leitura (mode=ro).
BANCO_ASSINATURAS = Path(
    os.getenv("CAMPANHA_BANCO_ASSINATURAS", str(BASE_DIR / "dados" / "assinaturas.db"))
)

# Banco proprio da campanha (fila, envios, opt-out). Arquivo novo.
BANCO_CAMPANHA = Path(
    os.getenv("CAMPANHA_BANCO", str(BASE_DIR / "dados" / "campanha.db"))
)

MARCA = os.getenv("CAMPANHA_MARCA", "ConnectTV").strip() or "ConnectTV"

# Numero que vai disparar a campanha (o mesmo pareado no dispositivo vinculado).
# Fica fora dos alvos: a campanha nunca manda mensagem para o proprio numero.
NUMERO_REMETENTE_BRUTO = os.getenv("CAMPANHA_NUMERO", "5511992501859").strip()
NUMERO_TESTE_BRUTO = os.getenv("CAMPANHA_NUMERO_TESTE", "").strip()

# Pasta dos lotes exportados em arquivo (fase 1, sem envio).
PASTA_SAIDA = Path(os.getenv("CAMPANHA_SAIDA", str(BASE_DIR / "dados")))


def numero_remetente() -> str:
    """Remetente normalizado (55DDDNUMERO) ou "" se o valor for invalido."""
    from .contatos import normalizar

    return normalizar(NUMERO_REMETENTE_BRUTO) or ""


def numero_teste() -> str:
    """Numero de teste (destinatario autorizado) ou "" se nao configurado."""
    from .contatos import normalizar

    return normalizar(NUMERO_TESTE_BRUTO) or ""

# "previa"  -> nada e enviado (padrao historico)
# "arquivo" -> gera um JSONL para conferencia manual; ainda sem rede
# "real"    -> libera o conector (fase 2); exige tambem a trava abaixo
# Trava de seguranca. Enquanto False, POST /campanha/ativar responde 409 mesmo
# que o modo seja alterado: nao existe caminho de envio real no codigo.
# Liberada em 16/11/2026, depois do pareamento do dispositivo e com o worker
# recusando enviar sem modo real + campanha ativa. Para desligar tudo de novo,
# volte para False (os testes de seguranca cobrem os dois estados).
ENVIO_REAL_HABILITADO = True

MODO = os.getenv("CAMPANHA_MODO", "real").strip().lower()
MODO_REAL = "real"
MODOS_VALIDOS = ("previa", "arquivo", "real")

# Reserva de alvo pelo conector: se o worker morrer no meio, o alvo volta
# sozinho para a fila depois desse tempo.
CONECTOR_RESERVA_MINUTOS = 15

# Rampa de aquecimento: mensagens por dia util.
RAMPA = (10, 20, 30)
CAP_DIARIO = RAMPA[-1]

# Horarios em que a campanha pode operar (hora local).
JANELAS = (("09:00", "11:30"), ("14:00", "17:30"))

# Envio manual: quando False, a campanha ativa pode enviar a qualquer hora e
# em qualquer dia; as janelas acima ficam só como referencia/para religar.
# Ligar o envio fora de horario comercial aumenta o risco de bloqueio do
# WhatsApp, por isso o padrao e manual (decisao do operador no painel).
# Para voltar a respeitar as janelas: CAMPANHA_JANELAS=1.
RESPEITAR_JANELAS = os.getenv("CAMPANHA_JANELAS", "0").strip() == "1"

# Segunda a sexta (0 = segunda). So vale quando RESPEITAR_JANELAS = True.
DIAS_SEMANA = (0, 1, 2, 3, 4)

# Ritmo humano entre um envio e o proximo.
INTERVALO_MIN = 90
INTERVALO_MAX = 240
PAUSA_CADA = 10
PAUSA_MIN = 600
PAUSA_MAX = 1200

# Nao repetir contato antes disso.
COOLDOWN_DIAS = 60
MAX_TENTATIVAS = 1

# Pausa automatica: se o envio falhar N vezes seguidas, a campanha se desliga
# sozinha em vez de continuar tentando. 0 desliga a pausa automatica.
MAX_FALHAS_SEGUIDAS = 3

# Log do worker (health check no painel). O worker escreve, a API le.
LOG_WORKER = Path(
    os.getenv("CAMPANHA_LOG_WORKER", str(BASE_DIR / "dados" / "campanha-worker.log"))
)

# Limites de tela (nao de envio).
LIMITE_PREVIA = 20
LIMITE_FILA = 500

# Midia (fase 2). Desligada por padrao: o pacote so cataloga os arquivos da
# pasta aprovada. Nao existe caminho de envio de imagem neste codigo.
MIDIA_HABILITADA = False
# Regra de ouro: imagem NUNCA no primeiro contato. So depois que o cliente
# responder. Virar isso e decisao sua e aumenta muito o risco de bloqueio.
MIDIA_NO_PRIMEIRO_CONTATO = False
MIDIA_PASTA = Path(
    os.getenv("CAMPANHA_MIDIA", str(BASE_DIR / "dados" / "midia"))
)
MIDIA_FORMATOS = ("jpg", "jpeg", "png", "webp")
MIDIA_TAMANHO_MAX_MB = 2
# Legenda do WhatsApp tem limite de 1024 caracteres.
MIDIA_LIMITE_LEGENDA = 1024

# Status que nunca entram em campanha.
STATUS_FORA = ("CANCELADO", "ATIVO", "TESTE")

# Situacoes gravadas em envios.
SITUACOES_ENVIADO = ("enviado", "simulado")
