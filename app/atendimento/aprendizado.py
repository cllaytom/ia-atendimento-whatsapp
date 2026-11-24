from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Conversa, Duvida, agora
from . import conhecimento
from .texto import normalizar

LIMITE_PERGUNTA = 600


def _limpar(texto: str | None) -> str:
    return " ".join((texto or "").split())[:LIMITE_PERGUNTA]


def registrar(db: Session, conversa: Conversa, pergunta: str) -> Duvida | None:
    """Guarda uma pergunta que o agente nao soube responder.

    Evita duplicar a mesma pergunta pendente para o mesmo contato.
    """
    limpo = _limpar(pergunta)
    if len(limpo) < 3:
        return None

    pendentes = db.scalars(
        select(Duvida).where(
            Duvida.status == "pendente",
            Duvida.contato == conversa.contato,
        )
    ).all()
    chave = normalizar(limpo)
    for existente in pendentes:
        if normalizar(existente.pergunta) == chave:
            existente.criada_em = agora()
            db.add(existente)
            db.flush()
            return existente

    duvida = Duvida(
        conversa_id=conversa.id,
        contato=conversa.contato,
        pergunta=limpo,
        contexto=conversa.etapa,
        status="pendente",
    )
    db.add(duvida)
    db.flush()
    return duvida


def listar(
    db: Session, status: str | None = None, limite: int = 100
) -> list[Duvida]:
    stmt = select(Duvida).order_by(Duvida.criada_em.desc()).limit(limite)
    if status:
        stmt = stmt.where(Duvida.status == status)
    return list(db.scalars(stmt).all())


def responder(
    db: Session,
    duvida: Duvida,
    resposta: str,
    salvar_na_base: bool = True,
) -> Duvida:
    texto = (resposta or "").strip()
    if not texto:
        raise ValueError("Informe a resposta.")

    duvida.resposta = texto
    duvida.status = "respondida"
    duvida.respondida_em = agora()
    db.add(duvida)

    if salvar_na_base:
        conhecimento.adicionar(duvida.pergunta, texto)

    db.commit()
    db.refresh(duvida)
    return duvida


def ignorar(db: Session, duvida: Duvida) -> Duvida:
    duvida.status = "ignorada"
    duvida.respondida_em = agora()
    db.add(duvida)
    db.commit()
    db.refresh(duvida)
    return duvida
