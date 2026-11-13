from __future__ import annotations

import re
import unicodedata


def normalizar(texto: str | None) -> str:
    """Deixa o texto minusculo, sem acentos e com espacos simples."""
    valor = unicodedata.normalize("NFKD", texto or "")
    valor = valor.encode("ascii", "ignore").decode("ascii").lower()
    valor = re.sub(r"\s+", " ", valor).strip()
    return valor


def tem(texto: str, *termos: str) -> bool:
    """Busca termos curtos como palavra inteira e frases como substring."""
    for termo in termos:
        termo = normalizar(termo)
        if not termo:
            continue
        if " " in termo:
            if termo in texto:
                return True
        elif re.search(rf"\b{re.escape(termo)}\b", texto):
            return True
    return False


def resposta_sim_nao(texto: str) -> bool | None:
    """Interpreta sim/nao. Retorna None quando nao da para saber."""
    if tem(texto, "nao sei", "nao lembro", "talvez", "depende"):
        return None
    if tem(texto, "nao", "nunca", "negativo", "nem"):
        return False
    if tem(
        texto,
        "sim",
        "claro",
        "positivo",
        "fiz",
        "recarreguei",
        "tenho",
        "ja",
        "ok",
        "isso",
        "pode",
        "confirmo",
        "correto",
    ):
        return True
    return None


def extrair_operadora(texto: str) -> str | None:
    """Retorna TIM, Vivo, OUTRA ou None."""
    if tem(texto, "tim"):
        return "TIM"
    if tem(texto, "vivo"):
        return "Vivo"
    if tem(texto, "claro", "oi", "nextel", "algar", "sercomtel"):
        return "OUTRA"
    return None


def extrair_plano_iptv(texto: str) -> str | None:
    if tem(texto, "completo", "completa") or re.search(r"\b2\b", texto):
        return "completo"
    if tem(texto, "basico", "basica", "simples") or re.search(r"\b3\b", texto):
        return "basico"
    return None


def parece_pergunta(texto: str) -> bool:
    return "?" in texto or tem(
        texto,
        "quanto",
        "qual",
        "quais",
        "como",
        "onde",
        "quando",
        "tem",
        "teria",
        "da pra",
        "da para",
        "posso",
        "aceita",
    )


def somente_digitos(texto: str) -> str:
    return re.sub(r"\D", "", texto or "")
