from __future__ import annotations

import os
from pathlib import Path

from ..config import DATA_DIR

NOME_NEGOCIO = os.getenv("NOME_NEGOCIO", "ConnectTV")
LINK_APP_ANDROID = os.getenv("LINK_APP_ANDROID", "").strip()
APP_IPTV_PADRAO = os.getenv("APP_IPTV_PADRAO", "").strip()
ALERTA_WHATSAPP = os.getenv("ALERTA_WHATSAPP", "5511942432179").strip()
ALERTA_WEBHOOK_URL = os.getenv("ALERTA_WEBHOOK_URL", "").strip()

IA_BASE_URL = os.getenv("IA_BASE_URL", "").strip().rstrip("/")
IA_API_KEY = os.getenv("IA_API_KEY", "").strip()
IA_MODELO = os.getenv("IA_MODELO", "openai/gpt-oss-120b").strip()
IA_TIMEOUT = float(os.getenv("IA_TIMEOUT", "25"))

IA_FALLBACK_BASE_URL = os.getenv("IA_FALLBACK_BASE_URL", "").strip().rstrip("/")
IA_FALLBACK_API_KEY = os.getenv("IA_FALLBACK_API_KEY", "").strip()
IA_FALLBACK_MODELO = os.getenv("IA_FALLBACK_MODELO", "llama3.1:8b").strip()

ARQUIVO_APLICATIVOS = Path(os.getenv("ARQUIVO_APLICATIVOS", DATA_DIR / "aplicativos.json"))
ARQUIVO_CONHECIMENTO = Path(os.getenv("ARQUIVO_CONHECIMENTO", DATA_DIR / "conhecimento.json"))


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
TRANSFERIR_DUVIDA = _bool_env("ATENDIMENTO_TRANSFERIR_DUVIDA", False)


def ia_ativa() -> bool:
    return bool(IA_BASE_URL and IA_API_KEY) or bool(IA_FALLBACK_BASE_URL)
