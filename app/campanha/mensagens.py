"""Mensagens da campanha: padrao, variacoes e saida (opt-out).

Regras de conteudo pensadas para reduzir risco de bloqueio:
- sem link no primeiro contato;
- sem imagem, audio ou arquivo;
- texto curto, pessoal e diferente entre contatos;
- toda mensagem informa como pedir para sair.
"""

from __future__ import annotations

from . import config
from .contatos import primeiro_nome

PADRAO = (
    "Olá, {nome}! Tudo bem?\n\n"
    "Sou da " + config.MARCA + " e estou entrando em contato sobre a Internet "
    "Ilimitada e o IPTV com canais.\n\n"
    "Verifiquei que já tivemos contato sobre internet e TV. Tem interesse em "
    "fazer um teste gratuito de 1 dia?\n\n"
    "Se preferir não receber mensagens, responda SAIR."
)

VARIANTES = (
    PADRAO,
    (
        "Oi, {nome}! Como você está?\n\n"
        "Aqui é da " + config.MARCA + ". Vi que você já foi nosso cliente de "
        "internet/IPTV e passei para saber se ainda tem interesse.\n\n"
        "Estamos liberando 1 dia de teste grátis, sem compromisso. Quer que eu "
        "te explique como funciona?\n\n"
        "Se não quiser receber mensagens, responda SAIR."
    ),
    (
        "Olá, {nome}! Passando rapidinho da " + config.MARCA + ".\n\n"
        "Você já falou com a gente sobre internet ilimitada e canais de TV. "
        "Ainda faz sentido para você hoje?\n\n"
        "Se tiver interesse, libero um teste de 1 dia sem custo para você "
        "conhecer.\n\n"
        "Para não receber mais mensagens, responda SAIR."
    ),
)

RODAPE = "Se preferir não receber mensagens, responda SAIR."

# Legenda que acompanha o flyer na fase 2. Curta de proposito: ela so sai
# DEPOIS que o cliente respondeu, entao nao repete a abordagem inicial.
LEGENDA_PADRAO = (
    "Segue o flyer com os planos e valores.\n\n"
    "Qualquer dúvida me chama aqui que eu te explico.\n\n"
    "Se preferir não receber mensagens, responda SAIR."
)


def garantir_optout(texto: str) -> str:
    """Toda mensagem precisa de uma forma clara de pedir para sair."""
    if "SAIR" in (texto or "").upper():
        return texto
    return (texto.rstrip() + "\n\n" + RODAPE).strip()


def legenda_padrao(extra: str = "") -> str:
    """Legenda do flyer, sempre com a linha de opt-out."""
    texto = LEGENDA_PADRAO.strip()
    if extra.strip():
        texto = texto.replace("\n\nSe preferir", "\n\n" + extra.strip() + "\n\nSe preferir")
    return garantir_optout(texto)


def renderizar(modelo: str, nome: str | None = None, usuario: str | None = None) -> str:
    """Troca {nome} pelo primeiro nome e garante a linha de opt-out."""
    humano = primeiro_nome(nome, usuario)
    texto = (modelo or PADRAO).strip()
    if humano:
        texto = texto.replace("{nome}", humano)
    else:
        texto = (
            texto.replace("Olá, {nome}!", "Olá!")
            .replace("Oi, {nome}!", "Oi!")
            .replace(", {nome}", "")
            .replace("{nome}", "")
        )
    return garantir_optout(texto)


def variantes() -> tuple[str, ...]:
    return VARIANTES
