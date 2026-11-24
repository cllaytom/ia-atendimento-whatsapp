"""Parametros de envio ajustaveis no painel.

Os valores ficam no banco proprio da campanha (tabela `estado`, chave
`parametros`). Sem nenhum valor salvo, tudo cai nos padroes de `config`, entao
o comportamento historico continua igual. O worker nao le estes valores: ele
pergunta ao conector, que aplica os overrides a cada envio.
"""

from __future__ import annotations

import json

from . import armazenamento, config

CHAVE = "parametros"

LIMITES = {
    "cota_diaria": (0, 100),
    "intervalo_min": (10, 3600),
    "intervalo_max": (10, 3600),
    "pausa_cada": (1, 100),
    "pausa_min": (30, 7200),
    "pausa_max": (30, 7200),
    "cooldown_dias": (0, 365),
    "max_tentativas": (1, 5),
    "max_falhas_seguidas": (0, 20),
}


def padroes() -> dict:
    """Valores de fabrica (config.py), usados quando nada foi salvo."""
    return {
        # 0 = usar a rampa de aquecimento 10 -> 20 -> 30.
        "cota_diaria": 0,
        "intervalo_min": int(config.INTERVALO_MIN),
        "intervalo_max": int(config.INTERVALO_MAX),
        "pausa_cada": int(config.PAUSA_CADA),
        "pausa_min": int(config.PAUSA_MIN),
        "pausa_max": int(config.PAUSA_MAX),
        "cooldown_dias": int(config.COOLDOWN_DIAS),
        "max_tentativas": int(config.MAX_TENTATIVAS),
        # 0 = nunca pausar sozinha.
        "max_falhas_seguidas": int(config.MAX_FALHAS_SEGUIDAS),
        "respeitar_janelas": bool(config.RESPEITAR_JANELAS),
    }


def limites() -> dict:
    return {chave: {"min": faixa[0], "max": faixa[1]} for chave, faixa in LIMITES.items()}


def salvos() -> dict:
    """Somente o que foi salvo no painel (pode ser vazio)."""
    bruto = armazenamento.parametros_salvos()
    if not bruto:
        return {}
    try:
        dados = json.loads(bruto)
    except (TypeError, ValueError):
        return {}
    if not isinstance(dados, dict):
        return {}
    validos: dict = {}
    for chave in padroes():
        if chave not in dados:
            continue
        if chave == "respeitar_janelas":
            validos[chave] = bool(dados[chave])
        else:
            try:
                validos[chave] = int(dados[chave])
            except (TypeError, ValueError):
                continue
    return validos


def atuais() -> dict:
    """Padroes + overrides salvos. E o que o conector usa de verdade."""
    valores = padroes()
    valores.update(salvos())
    return valores


def validar(dados: dict) -> dict:
    """Valida um lote de overrides e devolve o conjunto completo para salvar."""
    valores = atuais()

    if "respeitar_janelas" in dados:
        if not isinstance(dados["respeitar_janelas"], bool):
            raise ValueError("respeitar_janelas deve ser true ou false")
        valores["respeitar_janelas"] = dados["respeitar_janelas"]

    for chave, (minimo, maximo) in LIMITES.items():
        if chave not in dados:
            continue
        valor = dados[chave]
        if isinstance(valor, bool) or not isinstance(valor, (int, float)):
            raise ValueError(f"{chave} deve ser um numero inteiro")
        if int(valor) != valor:
            raise ValueError(f"{chave} deve ser um numero inteiro")
        valor = int(valor)
        if valor < minimo or valor > maximo:
            raise ValueError(f"{chave} deve ficar entre {minimo} e {maximo}")
        valores[chave] = valor

    if valores["intervalo_min"] > valores["intervalo_max"]:
        raise ValueError("intervalo minimo nao pode ser maior que o intervalo maximo")
    if valores["pausa_min"] > valores["pausa_max"]:
        raise ValueError("pausa minima nao pode ser maior que a pausa maxima")

    return valores


def salvar(dados: dict) -> dict:
    valores = validar(dados)
    armazenamento.salvar_parametros_json(json.dumps(valores, sort_keys=True))
    return valores


def restaurar() -> dict:
    armazenamento.limpar_parametros()
    return atuais()
