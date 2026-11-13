from __future__ import annotations

"""Leitura de historicos exportados do WhatsApp (.txt).

O objetivo nao e treinar o modelo: o arquivo vira uma lista de pares
pergunta/resposta para o time revisar e salvar na base de conhecimento.
"""

import re

from . import config, conhecimento
from .texto import normalizar

# Formato exportado pelo WhatsApp:
#   12/11/2026 14:33 - João: oi
#   [12/11/2026, 14:33:26] ConnectTV: Olá!
_LINHA = re.compile(
    r"^\s*[\[\(]?"
    r"(?P<data>\d{1,2}/\d{1,2}/\d{2,4})[,\s]+"
    r"(?P<hora>\d{1,2}:\d{2}(?::\d{2})?)[\]\)]?\s*[-–—]?\s*"
    r"(?P<autor>[^:]{1,80}):\s?(?P<texto>.*)$"
)

_MIDIA = (
    "arquivo de midia oculto",
    "midia omitida",
    "midia oculta",
    "imagem ocultada",
    "foto oculta",
    "audio omitido",
    "video omitido",
    "figurinha omitida",
    "gif omitido",
    "documento omitido",
    "contato omitido",
)

_SAUDACOES = {
    "oi",
    "ola",
    "opa",
    "eai",
    "e ai",
    "bom dia",
    "boa tarde",
    "boa noite",
    "tudo bem",
    "tudo bom",
    "ok",
    "blz",
    "beleza",
    "obrigado",
    "obrigada",
    "valeu",
    "sim",
    "nao",
    "quero",
}

_SISTEMA = (
    "as mensagens e as chamadas sao protegidas",
    "as mensagens e chamadas sao protegidas",
    "voce entrou usando",
    "criptografia de ponta a ponta",
)


def _parece_sistema(autor: str) -> bool:
    alvo = normalizar(autor)
    return any(marca in alvo for marca in _SISTEMA)


def _tem_midia(texto: str) -> bool:
    alvo = normalizar(texto)
    return any(marca in alvo for marca in _MIDIA)


def extrair_mensagens(texto: str) -> list[dict]:
    """Converte o texto exportado em uma lista de mensagens."""
    mensagens: list[dict] = []
    for bruta in (texto or "").splitlines():
        achado = _LINHA.match(bruta)
        if achado:
            autor = achado.group("autor").strip()
            if not autor or _parece_sistema(autor):
                continue
            mensagens.append(
                {
                    "autor": autor,
                    "texto": achado.group("texto").strip(),
                    "data": achado.group("data"),
                    "hora": achado.group("hora"),
                }
            )
            continue
        # Linha sem data/hora: continuacao da mensagem anterior.
        if mensagens and bruta.strip() and not _parece_sistema(bruta):
            mensagens[-1]["texto"] = (
                f"{mensagens[-1]['texto']}\n{bruta.strip()}".strip()
            )
    return mensagens


def _nomes_negocio(negocio: str | None) -> set[str]:
    nomes: set[str] = set()
    for nome in (negocio, config.NOME_NEGOCIO):
        alvo = normalizar(nome)
        if alvo:
            nomes.add(alvo)
    return nomes


def _eh_negocio(autor: str, nomes: set[str]) -> bool:
    alvo = normalizar(autor)
    if not alvo:
        return False
    compacto = re.sub(r"[^a-z0-9]", "", alvo)
    for nome in nomes:
        compacto_nome = re.sub(r"[^a-z0-9]", "", nome)
        if not compacto_nome:
            continue
        if compacto == compacto_nome:
            return True
        if len(compacto_nome) >= 4 and compacto_nome in compacto:
            return True
    return False


def _limpar(texto: str, limite: int = 600) -> str:
    return " ".join((texto or "").split())[:limite]


def _pergunta_valida(texto: str) -> bool:
    alvo = normalizar(texto)
    if len(alvo) < 6 or alvo in _SAUDACOES:
        return False
    if _tem_midia(texto):
        return False
    if not re.search(r"[a-z]", alvo):
        return False
    return "?" in texto or len(alvo.split()) >= 3


def _resposta_valida(texto: str) -> bool:
    alvo = normalizar(texto)
    if len(alvo) < 8 or alvo in _SAUDACOES:
        return False
    return not _tem_midia(texto)


def analisar(
    texto: str,
    negocio: str | None = None,
    limite: int = 200,
) -> dict:
    """Le o historico e devolve pares pergunta/resposta para revisao."""
    mensagens = extrair_mensagens(texto)
    autores: list[str] = []
    for mensagem in mensagens:
        if mensagem["autor"] not in autores:
            autores.append(mensagem["autor"])

    nomes = _nomes_negocio(negocio)
    negocio_autores = {
        autor for autor in autores if _eh_negocio(autor, nomes)
    }

    candidatos: list[dict] = []
    vistos: set[str] = set()
    for indice, mensagem in enumerate(mensagens[:-1]):
        if mensagem["autor"] in negocio_autores:
            continue
        resposta = mensagens[indice + 1]
        if resposta["autor"] == mensagem["autor"]:
            continue
        if negocio_autores and resposta["autor"] not in negocio_autores:
            continue

        pergunta = _limpar(mensagem["texto"])
        resposta_texto = _limpar(resposta["texto"])
        if not _pergunta_valida(pergunta) or not _resposta_valida(resposta_texto):
            continue

        chave = normalizar(pergunta)
        if chave in vistos:
            continue
        vistos.add(chave)

        candidatos.append(
            {
                "pergunta": pergunta,
                "resposta": resposta_texto,
                "contato": mensagem["autor"],
                "data": mensagem["data"],
                "hora": mensagem["hora"],
                "ja_na_base": bool(conhecimento.buscar(pergunta)),
            }
        )
        if len(candidatos) >= limite:
            break

    return {
        "autores": autores,
        "negocio_detectado": sorted(negocio_autores),
        "mensagens": len(mensagens),
        "total": len(candidatos),
        "candidatos": candidatos,
    }
