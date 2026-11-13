from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def agora() -> datetime:
    return datetime.now(timezone.utc)


class Evento(Base):
    """Auditoria das acoes do atendimento (ex.: transferencia para humano)."""

    __tablename__ = "eventos"

    id: Mapped[int] = mapped_column(primary_key=True)
    entidade: Mapped[str] = mapped_column(String(40), index=True)
    entidade_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    acao: Mapped[str] = mapped_column(String(40))
    antes: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    depois: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    origem: Mapped[str] = mapped_column(String(40), default="atendimento")
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)


class Conversa(Base):
    """Atendimento de um cliente no WhatsApp (ou no simulador).

    estado: ia | aguardando_humano | humano | encerrada
    etapa:  etapa atual da qualificacao (menu, internet_operadora, iptv_foto...)
    """

    __tablename__ = "conversas"

    id: Mapped[int] = mapped_column(primary_key=True)
    canal: Mapped[str] = mapped_column(String(30), default="simulador")
    contato: Mapped[str] = mapped_column(String(80), index=True)
    nome: Mapped[str | None] = mapped_column(String(120), nullable=True)
    estado: Mapped[str] = mapped_column(String(20), default="ia", index=True)
    etapa: Mapped[str] = mapped_column(String(40), default="menu")
    dados: Mapped[dict] = mapped_column(JSON, default=dict)
    motivo_transferencia: Mapped[str | None] = mapped_column(String(80), nullable=True)
    resumo: Mapped[str | None] = mapped_column(Text, nullable=True)
    alerta_enviado_em: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    ultima_mensagem_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=agora, index=True
    )
    criada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)
    atualizada_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=agora, onupdate=agora
    )

    mensagens: Mapped[list[MensagemAtendimento]] = relationship(
        back_populates="conversa",
        cascade="all, delete-orphan",
        order_by="MensagemAtendimento.id",
    )


class MensagemAtendimento(Base):
    """Mensagem trocada na conversa. autor: cliente | ia | humano | sistema."""

    __tablename__ = "mensagens_atendimento"

    id: Mapped[int] = mapped_column(primary_key=True)
    conversa_id: Mapped[int] = mapped_column(
        ForeignKey("conversas.id", ondelete="CASCADE"), index=True
    )
    autor: Mapped[str] = mapped_column(String(20))
    tipo: Mapped[str] = mapped_column(String(20), default="texto")
    texto: Mapped[str] = mapped_column(Text, default="")
    metadados: Mapped[dict] = mapped_column(JSON, default=dict)
    criada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)

    conversa: Mapped[Conversa] = relationship(back_populates="mensagens")


class Duvida(Base):
    """Pergunta do cliente que o agente nao soube responder.

    Serve de fila de aprendizado: o atendente responde e, se quiser, a resposta
    vira uma entrada da base de conhecimento para as proximas conversas.
    """

    __tablename__ = "duvidas_atendimento"

    id: Mapped[int] = mapped_column(primary_key=True)
    conversa_id: Mapped[int | None] = mapped_column(
        ForeignKey("conversas.id", ondelete="SET NULL"), nullable=True, index=True
    )
    contato: Mapped[str] = mapped_column(String(80), default="", index=True)
    pergunta: Mapped[str] = mapped_column(Text)
    contexto: Mapped[str | None] = mapped_column(String(40), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pendente", index=True)
    resposta: Mapped[str | None] = mapped_column(Text, nullable=True)
    criada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)
    respondida_em: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
