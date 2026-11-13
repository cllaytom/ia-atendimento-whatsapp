from __future__ import annotations

import random
import time

from . import config


def calcular(texto: str = "") -> float:
    """Calcula um tempo de resposta humano e variavel, em segundos.

    Combina uma pausa base aleatoria com o tempo proporcional ao tamanho da
    mensagem e aplica uma variacao final. O resultado fica entre PAUSA_MIN e
    PAUSA_TETO. Use sempre esta funcao (em vez de sleep fixo) para o
    comportamento nao ficar robotico.
    """
    base = random.uniform(config.PAUSA_MIN, config.PAUSA_MAX)
    digitacao = max(0, len(texto or "")) * config.PAUSA_POR_CARACTERE
    total = (base + digitacao) * random.uniform(0.8, 1.25)
    # De vez em quando uma pausa extra, para nao criar um padrao previsivel.
    if random.random() < 0.15:
        total += random.uniform(0.8, 2.0)
    return round(max(config.PAUSA_MIN, min(config.PAUSA_TETO, total)), 2)


def esperar(texto: str = "") -> float:
    """Aguarda o tempo calculado. Retorna o atraso aplicado.

    Adapters de canal real (WhatsApp) devem chamar esta funcao antes de cada
    envio. Se o cliente estiver digitando, marque presenca de "digitando" no
    canal durante o atraso para ficar ainda mais natural.
    """
    atraso = calcular(texto)
    if config.PAUSA_ATIVA and atraso > 0:
        time.sleep(atraso)
    return atraso
