"""Ritmo humano para a campanha.

Adaptado de `ia atendimento/app/atendimento/pausas.py` (mesma logica de
variacao), mas copiado para a campanha para que este pacote continue
independente do robo de atendimento.
"""

from __future__ import annotations

import random

from . import parametros

# Pausa de "digitacao" antes de submeter uma mensagem (segundos).
DIGITACAO_MIN = 3.0
DIGITACAO_MAX = 8.0
DIGITACAO_TETO = 20.0
DIGITACAO_POR_CARACTERE = 0.03


def calcular(texto: str = "") -> float:
    """Tempo de digitacao variavel, proporcional ao tamanho da mensagem."""
    base = random.uniform(DIGITACAO_MIN, DIGITACAO_MAX)
    digitacao = max(0, len(texto or "")) * DIGITACAO_POR_CARACTERE
    total = (base + digitacao) * random.uniform(0.8, 1.25)
    if random.random() < 0.15:
        total += random.uniform(0.8, 2.0)
    return round(max(DIGITACAO_MIN, min(DIGITACAO_TETO, total)), 2)


def intervalo_entre_envios() -> float:
    """Espera entre um contato e o proximo (padrao 90 a 240 segundos)."""
    valores = parametros.atuais()
    return round(random.uniform(valores["intervalo_min"], valores["intervalo_max"]), 2)


def pausa_longa() -> float:
    """Pausa maior a cada N envios, para nao criar cadencia de robo."""
    valores = parametros.atuais()
    return round(random.uniform(valores["pausa_min"], valores["pausa_max"]), 2)


def deve_pausar_longa(posicao: int) -> bool:
    cada = parametros.atuais()["pausa_cada"]
    return posicao > 0 and posicao % cada == 0
