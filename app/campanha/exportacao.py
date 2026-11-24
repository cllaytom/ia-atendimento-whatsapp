"""Exportacao do lote da campanha para arquivo (fase 1, sem envio).

O arquivo serve para conferencia e para envio manual supervisionado. Ele nao
altera a fila, nao marca ninguem como enviado e nao mexe em cooldown.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from . import config


def exportar_lote(itens: list[dict], pasta: Path | None = None) -> dict:
    destino = pasta or config.PASTA_SAIDA
    destino.mkdir(parents=True, exist_ok=True)
    nome = "campanha-lote-" + datetime.now().strftime("%Y%m%d-%H%M%S") + ".jsonl"
    caminho = destino / nome

    with caminho.open("w", encoding="utf-8") as arquivo:
        for item in itens:
            registro = {
                "id": item.get("id"),
                "cliente": item.get("nome"),
                "telefone": item.get("telefone"),
                "produto": item.get("produto"),
                "vencimento": item.get("vencimento"),
                "texto": item.get("texto"),
                "status": item.get("status"),
            }
            arquivo.write(json.dumps(registro, ensure_ascii=False) + "\n")

    return {"arquivo": str(caminho), "nome": nome, "quantidade": len(itens)}
