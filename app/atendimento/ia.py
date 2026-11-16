from __future__ import annotations

import logging
import re
import time
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
    conteudo = (escolhas[0].get("message") or {}).get("content")
    if isinstance(conteudo, list):
        return "".join(
            (parte.get("text") or "") if isinstance(parte, dict) and parte.get("type") == "text"
            else parte if isinstance(parte, str) else ""
            for parte in conteudo
        )
    return conteudo if isinstance(conteudo, str) else ""


def _precos_permitidos(texto: str) -> bool:
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


def _consultar(base_url: str, api_key: str, modelo: str, payload: dict) -> tuple[dict | None, int | None]:
    timeout = max(0.1, min(config.IA_TIMEOUT, 8.0))
    cabecalhos = {"Content-Type": "application/json"}
    if api_key:
        cabecalhos["Authorization"] = f"Bearer {api_key}"

    for tentativa in range(2):
        try:
            resposta = httpx.post(
                f"{base_url}/chat/completions",
                headers=cabecalhos,
                json=payload,
                timeout=timeout,
            )
        except (httpx.TimeoutException, httpx.RequestError):
            return None, None

        status = resposta.status_code
        if status in (500, 502, 503, 504) and tentativa == 0:
            time.sleep(0.5)
            continue
        if status >= 400:
            return None, status
        try:
            resultado = resposta.json()
        except ValueError:
            return None, status
        if not isinstance(resultado, dict):
            return None, status
        return resultado, status
    return None, None


def _mensagens(historico: list[dict], etapa: str, dados: dict) -> list[dict]:
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
    return mensagens


def responder(historico: list[dict], etapa: str, dados: dict) -> RespostaIA | None:
    if not disponivel():
        logger.warning("IA desativada: configure Groq ou Ollama no .env e reinicie.")
        return None

    mensagens = _mensagens(historico, etapa, dados)
    if len(mensagens) == 1:
        return None

    payload = {"model": config.IA_MODELO, "messages": mensagens, "temperature": 0.25, "max_tokens": 400}
    texto = ""
    transferir = False

    if config.IA_BASE_URL and config.IA_API_KEY:
        resposta, status = _consultar(config.IA_BASE_URL, config.IA_API_KEY, config.IA_MODELO, payload)
        if resposta:
            texto = _extrair_conteudo(resposta).strip()
            transferir = MARCADOR_TRANSFERIR in texto
            texto = texto.replace(MARCADOR_TRANSFERIR, "").strip()
        elif status == 429:
            logger.warning("Groq atingiu limite; tentando Ollama.")

    if not texto and config.IA_FALLBACK_BASE_URL:
        payload["model"] = config.IA_FALLBACK_MODELO
        resposta, status = _consultar(
            config.IA_FALLBACK_BASE_URL,
            config.IA_FALLBACK_API_KEY,
            config.IA_FALLBACK_MODELO,
            payload,
        )
        if resposta:
            texto = _extrair_conteudo(resposta).strip()
            transferir = MARCADOR_TRANSFERIR in texto
            texto = texto.replace(MARCADOR_TRANSFERIR, "").strip()

    if not texto and not transferir:
        return None

    if texto and not (_precos_permitidos(texto) and _promessas_permitidas(texto)):
        logger.warning("Resposta da IA bloqueada por conflitar com o catalogo.")
        return None

    return RespostaIA(texto=texto, transferir=transferir, motivo="ia_identificou")
