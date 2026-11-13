from __future__ import annotations

import json
import re

from . import config
from .texto import normalizar


def carregar_mapa() -> dict[str, str]:
    """Le dados/aplicativos.json. Chaves: marca ou modelo; valor: nome do app."""
    arquivo = config.ARQUIVO_APLICATIVOS
    if not arquivo.exists():
        return {}
    try:
        dados = json.loads(arquivo.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(dados, dict):
        return {}
    return {
        str(chave): str(valor)
        for chave, valor in dados.items()
        if not str(chave).startswith("_")
        and str(valor).strip()
        and not str(valor).strip().upper().startswith("NOME_DO_")
    }


def buscar(marca: str | None, modelo: str | None, smart: bool | None) -> str | None:
    """Descobre o aplicativo pelo modelo do TV Box, marca da TV ou app padrao."""
    alvo = normalizar(" ".join(parte for parte in (marca, modelo) if parte))
    for chave, aplicativo in carregar_mapa().items():
        chave_normalizada = normalizar(chave)
        if not chave_normalizada:
            continue
        if " " in chave_normalizada:
            encontrou = chave_normalizada in alvo
        else:
            encontrou = bool(re.search(rf"\b{re.escape(chave_normalizada)}\b", alvo))
        if encontrou:
            return aplicativo
    if config.APP_IPTV_PADRAO:
        return config.APP_IPTV_PADRAO
    return None
