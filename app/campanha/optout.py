"""Deteccao de recusa / opt-out da campanha.

Reaproveita o vocabulario ja validado em `motor._controle_cliente`, com duas
diferencas deliberadas:

1. o bloqueio aqui e GLOBAL e persistente (o atendimento so silencia a
   conversa), porque campanha que insiste em quem recusou gera denuncia;
2. "nao tenho interesse" tambem entra na lista, mesmo sem ser recusa
   explicita de contato.
"""

from __future__ import annotations

import re
import unicodedata

PADROES_OPTOUT = (
    re.compile(
        r"\b(?:nao (?:me )?(?:mande|envie|manda|envia)(?: mais)? mensage(?:m|ns)|"
        r"pare de (?:me )?(?:mandar|enviar) mensage(?:m|ns)|"
        r"nao me contate|remov[ae] (?:meu|o) (?:numero|contato)|"
        r"quero ser removid[oa]|descadastr\w*)\b"
    ),
)

PADROES_RECUSA = (
    re.compile(
        r"\b(?:nao (?:quero|desejo)(?: mais)? "
        r"(?:servico|servicos|nada|contratar|comprar|assinar|escolher)|"
        r"nao tenho interesse|sem interesse|desisti|nao quero mais)\b"
    ),
)

# Respostas curtas que a propria mensagem pede ("responda SAIR").
EXATOS_OPTOUT = {
    "sair", "sair por favor", "quero sair", "pare", "parar", "pode parar",
    "cancelar", "cancele", "cancela", "nao",
}


def normalizar(texto: str | None) -> str:
    """Minusculo, sem acento e sem pontuacao, para comparar frases."""
    base = unicodedata.normalize("NFKD", str(texto or ""))
    base = base.encode("ascii", "ignore").decode("ascii").lower()
    base = re.sub(r"[^a-z0-9 ]", " ", base.replace("+", " mais "))
    return " ".join(base.split())


def detectar(texto: str | None) -> str | None:
    """Devolve "optout", "recusa" ou None."""
    limpo = normalizar(texto)
    if not limpo:
        return None
    if limpo in EXATOS_OPTOUT:
        return "optout"
    for padrao in PADROES_OPTOUT:
        if padrao.search(limpo):
            return "optout"
    for padrao in PADROES_RECUSA:
        if padrao.search(limpo):
            return "recusa"
    return None
