"""Normalizacao de telefone e nome para a campanha."""

from __future__ import annotations

import re

DDD_MIN = 11
DDD_MAX = 99


def normalizar(contato) -> str | None:
    """Devolve o telefone no formato 55DDDNUMERO ou None se invalido.

    Aceita o que ja existe na base: com/sem DDI, com parenteses, espacos,
    tracos e ponto. Nunca converte nome de contato em numero.
    """
    if contato is None:
        return None
    bruto = str(contato).strip()
    if not bruto or not re.fullmatch(r"[+0-9 ()\-\.]+", bruto):
        return None
    digitos = re.sub(r"\D", "", bruto)
    if not digitos:
        return None
    digitos = digitos.lstrip("0")
    if len(digitos) in (10, 11):  # sem DDI
        digitos = "55" + digitos
    if len(digitos) not in (12, 13) or not digitos.startswith("55"):
        return None
    ddd = int(digitos[2:4])
    if not DDD_MIN <= ddd <= DDD_MAX:
        return None
    resto = digitos[4:]
    if len(resto) == 9 and resto[0] != "9":
        return None  # nono digito de celular comecando errado
    return digitos


def mascarar(numero: str | None) -> str:
    """Mostra o numero sem expor tudo (para logs e listagens)."""
    if not numero or len(numero) < 8:
        return "—"
    return f"+{numero[:2]} {numero[2:4]} *****-{numero[-4:]}"


def primeiro_nome(nome: str | None = None, usuario: str | None = None) -> str:
    """Nome humano para a saudacao.

    Prioriza o usuario (como no painel), remove digitos e simbolos.
    "8DEBORA" -> "Debora", "LUCAS54X" -> "Lucas", vazio -> "".
    """
    base = (usuario or "").strip() or (nome or "").strip()
    if not base:
        return ""
    base = re.sub(r"\d+", " ", base)
    base = re.sub(r"[^A-Za-zÀ-ÿ ]+", " ", base)
    partes = [p for p in base.split() if len(p) >= 2]
    if not partes:
        return ""
    parte = partes[0]
    return parte[:1].upper() + parte[1:].lower()
