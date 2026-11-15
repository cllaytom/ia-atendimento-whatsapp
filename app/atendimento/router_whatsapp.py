"""Ponte de WhatsApp (canal nao oficial): /whatsapp/...

Use quando a conta de WhatsApp conectada a este app recebe a mensagem:

1. POST /whatsapp/receber  {contato, texto, nome}
   -> devolve as respostas do agente; envie cada uma para o cliente.
2. Se a resposta trouxer `alerta_humano: true`, envie o campo
   `alerta_para` (numero) e o campo `alerta_texto` para o dono do negocio.

Todas as rotas exigem o header X-API-Key, igual ao resto da API.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator

from ..security import verificar_api_key
from . import config, ponte_whatsapp

router = APIRouter(
    prefix="/whatsapp",
    tags=["whatsapp"],
    dependencies=[Depends(verificar_api_key)],
)


class MensagemRecebida(BaseModel):
    contato: str = Field(min_length=8, max_length=30, examples=["5511999990000"])
    texto: str | None = Field(default=None, max_length=4000)
    nome: str | None = Field(default=None, max_length=120)
    imagem: str | None = None

    @model_validator(mode="after")
    def exigir_conteudo(self):
        if not (self.texto or "").strip() and not self.imagem:
            raise ValueError("Envie um texto ou uma imagem.")
        return self


@router.post(
    "/receber",
    summary="Receber uma mensagem do WhatsApp e obter as respostas do agente",
)
def receber(payload: MensagemRecebida):
    try:
        resultado = ponte_whatsapp.receber(
            contato=payload.contato,
            texto=payload.texto or "",
            nome=payload.nome,
            imagem=payload.imagem,
        )
    except ValueError as erro:
        raise HTTPException(status_code=409, detail=str(erro)) from erro

    if resultado["alerta_humano"]:
        resultado["alerta_para"] = config.ALERTA_WHATSAPP
        resultado["alerta_texto"] = ponte_whatsapp.alerta_de_transferencia(
            payload.contato, resultado
        )
    return resultado


@router.get("/status/{contato}", summary="Situacao da conversa de um contato")
def situacao(contato: str):
    return ponte_whatsapp.status(contato)


@router.post("/encerrar/{contato}", summary="Encerrar a conversa de um contato")
def encerrar(contato: str):
    if not ponte_whatsapp.encerrar(contato):
        raise HTTPException(status_code=404, detail="Nenhuma conversa aberta.")
    return {"contato": ponte_whatsapp.normalizar_contato(contato), "encerrada": True}
