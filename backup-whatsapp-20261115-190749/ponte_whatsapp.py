"""Ponte para WhatsApp nao oficial (conta do usuario, sem API da Meta).

Como funciona
-------------
O atendente deste app conversa com o WhatsApp de verdade. Quando chega uma
mensagem de cliente, a ponte registra a mensagem e devolve o texto que o
atendente deve mandar de volta. O motor usado e o mesmo do simulador: mesma
base de conhecimento, mesmo catalogo, mesmas regras de transferencia.

Regra desta ponte: toda mensagem recebida vai para o agente (a pessoa que
quiser falar com um humano pede por "atendente" ou opcao 4).
"""

from __future__ import annotations

import re

from sqlalchemy import select

from ..database import SessionLocal
from ..models import Conversa
from . import config, motor

CANAL = "whatsapp"

# Numeros que falam pelo canal sao normalizados como 55DDDNUMERO.
_APENAS_DIGITOS = re.compile(r"\D+")


def normalizar_contato(bruto: str) -> str:
    """Deixa o numero no formato 55DDDNUMERO (sem +, espacos ou tracos)."""
    digitos = _APENAS_DIGITOS.sub("", bruto or "")
    if len(digitos) <= 11:
        digitos = "55" + digitos
    return digitos[:20]


def _conversa_aberta(db, contato: str) -> Conversa | None:
    return db.scalars(
        select(Conversa)
        .where(Conversa.contato == contato, Conversa.canal == CANAL)
        .where(Conversa.estado != motor.ESTADO_ENCERRADA)
        .order_by(Conversa.id.desc())
        .limit(1)
    ).first()


def receber(
    contato: str,
    texto: str,
    nome: str | None = None,
    imagem: str | None = None,
) -> dict:
    """Registra a mensagem do cliente e devolve as respostas do agente.

    Retorno:
        {
          "conversa_id": 12,
          "estado": "ia" | "aguardando_humano" | "humano",
          "respostas": ["texto 1", "texto 2"],
          "alerta_humano": True/False,
          "motivo": "..." (quando transferiu)
        }
    """
    contato = normalizar_contato(contato)
    if not contato:
        raise ValueError("Contato vazio.")
    texto = (texto or "").strip()

    db = SessionLocal()
    try:
        conversa = _conversa_aberta(db, contato)
        if conversa is None:
            conversa = motor.criar_conversa(
                db, contato=contato, nome=nome, canal=CANAL
            )

        novas = motor.processar_mensagem_cliente(
            db, conversa, texto=texto, imagem=imagem
        )
        db.refresh(conversa)

        respostas = [
            mensagem.texto for mensagem in novas if mensagem.autor == "ia"
        ]
        # Mensagens de sistema (o bloco "🔔 Transferido...") nao vao ao cliente.
        transferiu = conversa.estado in (
            motor.ESTADO_AGUARDANDO,
            motor.ESTADO_HUMANO,
        )
        return {
            "conversa_id": conversa.id,
            "estado": conversa.estado,
            "etapa": conversa.etapa,
            "respostas": [resposta for resposta in respostas if resposta],
            "alerta_humano": transferiu,
            "motivo": conversa.motivo_transferencia,
            "resumo": conversa.resumo,
        }
    finally:
        db.close()


def status(contato: str) -> dict:
    """Mostra em que pe esta a conversa de um contato (para o painel)."""
    contato = normalizar_contato(contato)
    db = SessionLocal()
    try:
        conversa = _conversa_aberta(db, contato)
        if conversa is None:
            return {"contato": contato, "existe": False}
        return {
            "contato": contato,
            "existe": True,
            "conversa_id": conversa.id,
            "estado": conversa.estado,
            "etapa": conversa.etapa,
            "dados": conversa.dados or {},
            "resumo": conversa.resumo,
        }
    finally:
        db.close()


def encerrar(contato: str) -> bool:
    """Encerra a conversa aberta do contato (proximo contato comeca do zero)."""
    contato = normalizar_contato(contato)
    db = SessionLocal()
    try:
        conversa = _conversa_aberta(db, contato)
        if conversa is None:
            return False
        conversa.estado = motor.ESTADO_ENCERRADA
        db.commit()
        return True
    finally:
        db.close()


def _texto_do_numero(contato: str) -> str:
    """Usado no alerta: 5511999990000 -> +55 11 99999-0000."""
    contato = normalizar_contato(contato)
    if len(contato) == 13:
        return f"+{contato[:2]} {contato[2:4]} {contato[4:9]}-{contato[9:]}"
    return "+" + contato


def alerta_de_transferencia(contato: str, resultado: dict) -> str:
    """Texto pronto para mandar ao numero de alerta (config.ALERTA_WHATSAPP)."""
    return (
        "🔔 *Atendimento humano necessário*\n"
        f"Cliente: {_texto_do_numero(contato)}\n"
        f"Motivo: {resultado.get('motivo') or 'não informado'}\n\n"
        f"{resultado.get('resumo') or ''}"
    ).strip()
