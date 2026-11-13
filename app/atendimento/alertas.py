from __future__ import annotations

import logging

import httpx

from ..models import Conversa, Evento, agora
from . import config

logger = logging.getLogger("atendimento.alertas")


def notificar(db, conversa: Conversa) -> None:
    """Registra e dispara o alerta de transferencia para o atendimento humano.

    No modo simulador o alerta aparece no painel. Se ALERTA_WEBHOOK_URL estiver
    configurado, o mesmo JSON tambem e enviado para n8n/Zapier/Make.
    """
    texto = (
        f"🔔 Atendimento humano necessário\n"
        f"Contato: {conversa.nome or conversa.contato} ({conversa.contato})\n"
        f"Motivo: {conversa.motivo_transferencia or 'não informado'}\n\n"
        f"{conversa.resumo or ''}"
    )
    logger.warning(
        "ALERTA WHATSAPP -> %s\n%s", config.ALERTA_WHATSAPP, texto
    )

    if config.ALERTA_WEBHOOK_URL:
        try:
            httpx.post(
                config.ALERTA_WEBHOOK_URL,
                json={
                    "evento": "transferencia_atendimento",
                    "conversa_id": conversa.id,
                    "canal": conversa.canal,
                    "contato": conversa.contato,
                    "nome": conversa.nome,
                    "motivo": conversa.motivo_transferencia,
                    "resumo": conversa.resumo,
                    "alerta_whatsapp": config.ALERTA_WHATSAPP,
                },
                timeout=6,
            )
        except Exception:
            logger.exception("Falha ao enviar o alerta para ALERTA_WEBHOOK_URL.")

    conversa.alerta_enviado_em = agora()
    db.add(
        Evento(
            entidade="conversa",
            entidade_id=conversa.id,
            acao="transferencia_humano",
            depois={
                "motivo": conversa.motivo_transferencia,
                "resumo": conversa.resumo,
                "canal": conversa.canal,
            },
            origem="atendimento",
        )
    )
