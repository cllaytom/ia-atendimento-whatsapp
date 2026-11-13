from __future__ import annotations

import json
import re

from . import config
from .texto import normalizar

# Palavras comuns que nao ajudam a identificar o assunto da pergunta.
PARADAS = {
    "a", "o", "as", "os", "de", "da", "do", "das", "dos", "e", "que",
    "em", "no", "na", "nos", "nas", "um", "uma", "para", "pra", "com",
    "por", "se", "me", "meu", "minha", "tem", "ter", "sobre", "qual",
    "quais", "quanto", "como", "onde", "quando", "voce", "voces", "ser",
    "sou", "esta", "esse", "essa", "isso", "aquilo", "mais", "muito",
    "pode", "posso", "faz", "fazer", "gostaria", "queria", "quero",
}

ASSUNTOS_PRODUTO = {
    "internet", "vpn", "iptv", "plano", "planos", "chip", "tim", "vivo",
    "recarga", "android", "iphone", "ios", "aplicativo", "app", "play",
    "store", "tv", "televisao", "smart", "box", "streamer", "streamers",
    "teste", "gratis", "preco", "valor", "mensalidade", "ativar",
    "ativacao", "instalar", "assinatura", "basico", "completo", "cartao",
    "boleto", "pix", "pagamento", "garantia", "cancelar", "cancelamento",
    "renovar", "renovacao", "vencimento", "suporte", "seguro", "segura",
    "seguranca", "confiavel", "confianca", "confiar", "golpe", "fraude",
    "virus", "hacker", "privacidade", "criptografia", "criptografado",
    "protegido", "protege", "net", "dados", "ilimitada", "ilimitado",
}


def _palavras(texto: str) -> list[str]:
    base = normalizar(texto)
    return [
        palavra
        for palavra in re.findall(r"[a-z0-9]+", base)
        if len(palavra) >= 3 and palavra not in PARADAS
    ]


def parece_produto(texto: str) -> bool:
    return bool(set(_palavras(texto)) & ASSUNTOS_PRODUTO)


def carregar() -> list[dict]:
    arquivo = config.ARQUIVO_CONHECIMENTO
    if not arquivo.exists():
        return []
    try:
        dados = json.loads(arquivo.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []

    if isinstance(dados, dict):
        dados = dados.get("entradas") or []
    if not isinstance(dados, list):
        return []

    entradas: list[dict] = []
    for item in dados:
        if not isinstance(item, dict):
            continue
        pergunta = str(item.get("pergunta") or "").strip()
        resposta = str(item.get("resposta") or "").strip()
        if not pergunta or not resposta:
            continue
        termos = item.get("termos")
        if isinstance(termos, list):
            termos = [str(termo).strip() for termo in termos if str(termo).strip()]
        else:
            termos = None
        entradas.append(
            {"pergunta": pergunta, "resposta": resposta, "termos": termos}
        )
    return entradas


def salvar(entradas: list[dict]) -> None:
    arquivo = config.ARQUIVO_CONHECIMENTO
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    conteudo = {
        "_instrucoes": (
            "Base de conhecimento do atendimento. Somente assuntos do produto "
            "vendido (internet ilimitada + VPN e IPTV). Cada item tem pergunta, "
            "resposta e, opcionalmente, termos que devem aparecer na mensagem "
            "do cliente."
        ),
        "entradas": entradas,
    }
    arquivo.write_text(
        json.dumps(conteudo, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _termos(entrada: dict) -> list[str]:
    termos = entrada.get("termos")
    if isinstance(termos, list) and termos:
        return [normalizar(termo) for termo in termos if termo]
    return _palavras(entrada.get("pergunta") or "")


def _pontuar(texto_normalizado: str, entrada: dict) -> float:
    termos = _termos(entrada)
    if not termos:
        return 0.0
    achados = 0
    for termo in termos:
        if not termo:
            continue
        if " " in termo:
            if termo in texto_normalizado:
                achados += 1
        elif re.search(rf"\b{re.escape(termo)}\b", texto_normalizado):
            achados += 1
    return achados / len(termos)


def buscar(texto: str) -> dict | None:
    alvo = normalizar(texto)
    if len(alvo) < 3:
        return None

    melhor: dict | None = None
    melhor_nota = 0.0
    for entrada in carregar():
        nota = _pontuar(alvo, entrada)
        if nota >= 0.6 and nota > melhor_nota:
            melhor = entrada
            melhor_nota = nota
    return melhor


def adicionar(
    pergunta: str,
    resposta: str,
    termos: list[str] | None = None,
) -> dict:
    pergunta = (pergunta or "").strip()
    resposta = (resposta or "").strip()
    if not pergunta or not resposta:
        raise ValueError("Informe a pergunta e a resposta.")

    entradas = carregar()
    chave = normalizar(pergunta)
    for entrada in entradas:
        if normalizar(entrada["pergunta"]) == chave:
            entrada["resposta"] = resposta
            if termos:
                entrada["termos"] = termos
            salvar(entradas)
            return entrada

    item = {"pergunta": pergunta, "resposta": resposta}
    if termos:
        item["termos"] = [termo for termo in termos if str(termo).strip()]
    entradas.append(item)
    salvar(entradas)
    return item


def remover(indice: int) -> bool:
    entradas = carregar()
    if indice < 0 or indice >= len(entradas):
        return False
    entradas.pop(indice)
    salvar(entradas)
    return True


def total() -> int:
    return len(carregar())


def para_prompt(texto: str = "", limite: int = 20, maximo: int = 8000) -> str:
    """Envia mais contexto da base para o Gemini interpretar perguntas variadas."""
    entradas = carregar()
    if not entradas:
        return ""

    alvo = normalizar(texto or "")
    ordenadas = sorted(
        enumerate(entradas),
        key=lambda par: (-_pontuar(alvo, par[1]) if alvo else 0.0, par[0]),
    )

    linhas: list[str] = []
    tamanho = 0
    for _, entrada in ordenadas[:limite]:
        resposta = " ".join(entrada["resposta"].split())
        if len(resposta) > 700:
            resposta = resposta[:697].rstrip() + "..."
        linha = f"- P: {entrada['pergunta']}\n  R: {resposta}"
        if tamanho + len(linha) > maximo:
            break
        linhas.append(linha)
        tamanho += len(linha) + 1
    return "\n".join(linhas)
