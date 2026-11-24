from __future__ import annotations

import os
from pathlib import Path

from ..config import DATA_DIR

# ---------------------------------------------------------------------------
# Dados do negocio (podem ser trocados no .env, sem mexer no codigo)
# ---------------------------------------------------------------------------
NOME_NEGOCIO = os.getenv("NOME_NEGOCIO", "ConnectTV")

# Link do aplicativo Android na Play Store. Se ficar vazio, o agente avisa que
# o atendente enviara o link na ativacao.
LINK_APP_ANDROID = os.getenv("LINK_APP_ANDROID", "").strip()

# Aplicativo de IPTV usado quando o aparelho nao estiver no mapa por marca/modelo.
# Ex.: APP_IPTV_PADRAO=IPTV Smarters Pro
APP_IPTV_PADRAO = os.getenv("APP_IPTV_PADRAO", "").strip()

# Numero que recebe o alerta de transferencia (formato 55DDDNUMERO).
ALERTA_WHATSAPP = os.getenv("ALERTA_WHATSAPP", "5511942432179").strip()

# Opcional: webhook (n8n, Zapier, Make...) que recebe o alerta em JSON.
ALERTA_WEBHOOK_URL = os.getenv("ALERTA_WEBHOOK_URL", "").strip()

# ---------------------------------------------------------------------------
# IA (qualquer endpoint compativel com OpenAI: Gemini, OpenAI, DeepSeek...)
# ---------------------------------------------------------------------------
IA_BASE_URL = os.getenv("IA_BASE_URL", "").strip().rstrip("/")
IA_API_KEY = os.getenv("IA_API_KEY", "").strip()
IA_MODELO = os.getenv("IA_MODELO", "gemini-2.0-flash").strip()
IA_TIMEOUT = float(os.getenv("IA_TIMEOUT", "25"))

# Mapa marca/modelo -> aplicativo de IPTV (arquivo JSON editavel).
ARQUIVO_APLICATIVOS = Path(
    os.getenv("ARQUIVO_APLICATIVOS", DATA_DIR / "aplicativos.json")
)

# Base de conhecimento editavel (perguntas e respostas sobre o produto vendido).
ARQUIVO_CONHECIMENTO = Path(
    os.getenv("ARQUIVO_CONHECIMENTO", DATA_DIR / "conhecimento.json")
)


# ---------------------------------------------------------------------------
# Pausa entre respostas (simula digitacao humana e reduz risco de ban)
# ---------------------------------------------------------------------------
def _bool_env(nome: str, padrao: bool) -> bool:
    valor = os.getenv(nome)
    if valor is None:
        return padrao
    return valor.strip().lower() not in {"", "0", "false", "nao", "não", "off"}


PAUSA_ATIVA = _bool_env("ATENDIMENTO_PAUSA_ATIVA", True)
PAUSA_MIN = float(os.getenv("ATENDIMENTO_PAUSA_MIN", "0.8"))
PAUSA_MAX = float(os.getenv("ATENDIMENTO_PAUSA_MAX", "2.5"))
PAUSA_TETO = float(os.getenv("ATENDIMENTO_PAUSA_TETO", "6.0"))
PAUSA_POR_CARACTERE = float(os.getenv("ATENDIMENTO_PAUSA_POR_CARACTERE", "0.008"))


def ia_ativa() -> bool:
    return bool(IA_BASE_URL and IA_API_KEY)
