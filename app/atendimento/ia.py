from __future__ import annotations

import logging
import re
from dataclasses import dataclass

import httpx

from . import config, conhecimento, oferta
from .prompts import sistema

logger = logging.getLogger("atendimento.ia")

MARCADOR_TRANSFERIR = "[[TRANSFERIR]]"


@dataclass
class RespostaIA:
    texto: str
    transferir: bool = False
    motivo: str = ""


def disponivel() -> bool:
    return config.ia_ativa()


def _extrair_conteudo(dados: dict) -> str:
    escolhas = dados.get("choices") or []
    if not escolhas:
        return ""
    mensagem = escolhas[0].get("message") or {}
    conteudo = mensagem.get("content")
    if isinstance(conteudo, list):
        partes = []
        for parte in conteudo:
            if isinstance(parte, dict) and parte.get("type") == "text":
                partes.append(parte.get("text") or "")
            elif isinstance(parte, str):
                partes.append(parte)
        return "".join(partes)
    return conteudo or ""


def _precos_permitidos(texto: str) -> bool:
    """Bloqueia respostas com valores que nao existem no catalogo."""
    for achado in re.finditer(r"R\$\s*([\d.]+)(?:,(\d{1,2}))?", texto):
        inteiro = achado.group(1).replace(".", "")
        decimal = achado.group(2) or "0"
        try:
            valor = float(f"{inteiro}.{decimal}")
        except ValueError:
            return False
        if valor not in oferta.PRECOS_VALIDOS:
            return False
    for achado in re.finditer(r"\b(\d{1,3})\s*reais\b", texto, re.IGNORECASE):
        if float(achado.group(1)) not in oferta.PRECOS_VALIDOS:
            return False
    return True


def _promessas_permitidas(texto: str) -> bool:
    minusculo = texto.lower()
    if re.search(r"\biphone\b|\bios\b|\bapple\b", minusculo):
        negacoes = ("não", "nao", "infelizmente", "apenas android", "somente android")
        if not any(negacao in minusculo for negacao in negacoes):
            return False
    if "teste" in minusculo:
        horas = re.findall(r"(\d+)\s*(?:h\b|horas?\b)", minusculo)
        if any(int(valor) != oferta.INTERNET_TRIAL_HORAS for valor in horas):
            return False
    return True


def responder(historico: list[dict], etapa: str, dados: dict) -> RespostaIA | None:
    """Consulta o modelo. Retorna None quando a IA nao esta configurada ou falhou."""
    if not disponivel():
        return None

    pergunta_atual = ""
    for item in reversed(historico):
        if item.get("autor") == "cliente" and (item.get("texto") or "").strip():
            pergunta_atual = item["texto"]
            break
    base_conhecimento = conhecimento.para_prompt(pergunta_atual)

    mensagens = [{"role": "system", "content": sistema(etapa, dados, base_conhecimento)}]
    for item in historico[-16:]:
        autor = item.get("autor")
        texto = (item.get("texto") or "").strip()
        if not texto or item.get("tipo") != "texto":
            continue
        if autor == "cliente":
            mensagens.append({"role": "user", "content": texto})
        elif autor in ("ia", "humano"):
            mensagens.append({"role": "assistant", "content": texto})

    if len(mensagens) == 1:
        return None

    payload = {
        "model": config.IA_MODELO,
        "messages": mensagens,
        "temperature": 0.25,
        "max_tokens": 400,
    }
    try:
        resposta = httpx.post(
            f"{config.IA_BASE_URL}/chat/completions",
            headers={
                "Authorization": f"Bearer {config.IA_API_KEY}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=config.IA_TIMEOUT,
        )
        resposta.raise_for_status()
        dados_resposta = resposta.json()
    except Exception:
        logger.exception("Falha ao consultar a IA; usando respostas roteirizadas.")
        return None

    texto = _extrair_conteudo(dados_resposta).strip()
    if not texto:
        return None

    transferir = MARCADOR_TRANSFERIR in texto
    texto = texto.replace(MARCADOR_TRANSFERIR, "").strip()

    if texto and not (_precos_permitidos(texto) and _promessas_permitidas(texto)):
        logger.warning("Resposta da IA bloqueada por conflitar com o catalogo: %s", texto)
        return None

    if not texto and not transferir:
        return None

    return RespostaIA(texto=texto, transferir=transferir, motivo="ia_identificou")
