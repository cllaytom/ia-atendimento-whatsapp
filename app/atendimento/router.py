from __future__ import annotations

import re
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Conversa, Duvida, MensagemAtendimento
from ..security import verificar_api_key
from . import (
    aplicativos,
    aprendizado,
    config,
    conhecimento,
    ia,
    motor,
    pausas,
)
from .schemas import (
    ConversaCriar,
    EntradaConhecimento,
    MensagemCliente,
    RespostaDuvida,
    RespostaHumano,
)

router = APIRouter(
    prefix="/atendimento",
    tags=["atendimento"],
    dependencies=[Depends(verificar_api_key)],
)

LIMITE_IMAGEM = 3_000_000  # caracteres do data URL (~2,2 MB)


def _iso(valor: datetime | None) -> str | None:
    if valor is None:
        return None
    if valor.tzinfo is None:
        return valor.isoformat() + "Z"
    return valor.isoformat()


def _mensagem_dict(mensagem: MensagemAtendimento) -> dict:
    metadados = mensagem.metadados or {}
    return {
        "id": mensagem.id,
        "autor": mensagem.autor,
        "tipo": mensagem.tipo,
        "texto": mensagem.texto,
        "imagem": metadados.get("imagem") if mensagem.tipo == "imagem" else None,
        "criada_em": _iso(mensagem.criada_em),
    }


def _conversa_dict(conversa: Conversa, previa: str | None = None) -> dict:
    return {
        "id": conversa.id,
        "canal": conversa.canal,
        "contato": conversa.contato,
        "nome": conversa.nome,
        "estado": conversa.estado,
        "etapa": conversa.etapa,
        "dados": conversa.dados or {},
        "motivo_transferencia": conversa.motivo_transferencia,
        "resumo": conversa.resumo,
        "alerta_enviado_em": _iso(conversa.alerta_enviado_em),
        "ultima_mensagem_em": _iso(conversa.ultima_mensagem_em),
        "criada_em": _iso(conversa.criada_em),
        "previa": previa,
    }


def _detalhe(db: Session, conversa: Conversa) -> dict:
    mensagens = db.scalars(
        select(MensagemAtendimento)
        .where(MensagemAtendimento.conversa_id == conversa.id)
        .order_by(MensagemAtendimento.id)
    ).all()
    return {
        "conversa": _conversa_dict(conversa),
        "mensagens": [_mensagem_dict(item) for item in mensagens],
    }


def _buscar(db: Session, conversa_id: int) -> Conversa:
    conversa = db.get(Conversa, conversa_id)
    if not conversa:
        raise HTTPException(status_code=404, detail="Conversa nao encontrada.")
    return conversa


@router.get("/config", summary="Configuracao visivel ao painel de atendimento")
def configuracao(db: Session = Depends(get_db)):
    mapa = aplicativos.carregar_mapa()
    pendentes = db.scalar(
        select(func.count(Duvida.id)).where(Duvida.status == "pendente")
    )
    return {
        "nome_negocio": config.NOME_NEGOCIO,
        "ia_ativa": ia.disponivel(),
        "modelo_ia": config.IA_MODELO if ia.disponivel() else None,
        "link_app_configurado": bool(config.LINK_APP_ANDROID),
        "app_iptv_padrao": config.APP_IPTV_PADRAO or None,
        "alerta_whatsapp": config.ALERTA_WHATSAPP,
        "aplicativos_configurados": len(mapa),
        "conhecimento_entradas": conhecimento.total(),
        "duvidas_pendentes": pendentes or 0,
        "modo": "simulador",
    }


@router.get("/conversas", summary="Listar conversas")
def listar(
    estado: str | None = Query(default=None),
    q: str | None = Query(default=None),
    limite: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    stmt = select(Conversa).order_by(Conversa.ultima_mensagem_em.desc()).limit(limite)
    if estado:
        stmt = stmt.where(Conversa.estado == estado)
    if q:
        termo = f"%{q.strip()}%"
        stmt = stmt.where(
            (Conversa.nome.ilike(termo)) | (Conversa.contato.ilike(termo))
        )

    itens = []
    for conversa in db.scalars(stmt).all():
        ultima = db.execute(
            select(MensagemAtendimento.tipo, MensagemAtendimento.texto)
            .where(MensagemAtendimento.conversa_id == conversa.id)
            .order_by(MensagemAtendimento.id.desc())
            .limit(1)
        ).first()
        if ultima is None:
            previa = None
        elif ultima.tipo == "imagem":
            previa = "📷 Foto enviada"
        else:
            previa = (ultima.texto or "").strip().replace("\n", " ")[:90]

        item = _conversa_dict(conversa, previa=previa)
        itens.append(item)

    aguardando = db.scalar(
        select(func.count(Conversa.id)).where(
            Conversa.estado == motor.ESTADO_AGUARDANDO
        )
    )
    return {"itens": itens, "total": len(itens), "aguardando": aguardando or 0}


@router.get("/alertas", summary="Conversas aguardando atendimento humano")
def alertas(db: Session = Depends(get_db)):
    conversas = db.scalars(
        select(Conversa)
        .where(Conversa.estado == motor.ESTADO_AGUARDANDO)
        .order_by(Conversa.ultima_mensagem_em)
    ).all()
    return {"itens": [_conversa_dict(conversa) for conversa in conversas]}


# ---------------------------------------------------------------------------
# Aprendizado: duvidas nao respondidas -> base de conhecimento
# ---------------------------------------------------------------------------
def _duvida_dict(db: Session, duvida: Duvida) -> dict:
    conversa = db.get(Conversa, duvida.conversa_id) if duvida.conversa_id else None
    return {
        "id": duvida.id,
        "conversa_id": duvida.conversa_id,
        "contato": duvida.contato,
        "nome": conversa.nome if conversa else None,
        "pergunta": duvida.pergunta,
        "contexto": duvida.contexto,
        "status": duvida.status,
        "resposta": duvida.resposta,
        "criada_em": _iso(duvida.criada_em),
        "respondida_em": _iso(duvida.respondida_em),
    }


@router.get("/duvidas", summary="Perguntas que o agente nao soube responder")
def listar_duvidas(
    status: str | None = Query(default="pendente"),
    limite: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    itens = aprendizado.listar(db, status=status, limite=limite)
    return {
        "itens": [_duvida_dict(db, duvida) for duvida in itens],
        "total": len(itens),
    }


@router.post(
    "/duvidas/{duvida_id}/responder",
    summary="Responder uma duvida e ensinar a base",
)
def responder_duvida(
    duvida_id: int,
    payload: RespostaDuvida,
    db: Session = Depends(get_db),
):
    duvida = db.get(Duvida, duvida_id)
    if not duvida:
        raise HTTPException(status_code=404, detail="Duvida nao encontrada.")
    if duvida.status != "pendente":
        raise HTTPException(status_code=409, detail="Duvida ja respondida.")
    try:
        aprendizado.responder(
            db, duvida, payload.resposta, payload.salvar_na_base
        )
    except ValueError as erro:
        raise HTTPException(status_code=400, detail=str(erro)) from erro
    return _duvida_dict(db, duvida)


@router.post("/duvidas/{duvida_id}/ignorar", summary="Ignorar uma duvida")
def ignorar_duvida(duvida_id: int, db: Session = Depends(get_db)):
    duvida = db.get(Duvida, duvida_id)
    if not duvida:
        raise HTTPException(status_code=404, detail="Duvida nao encontrada.")
    if duvida.status != "pendente":
        raise HTTPException(status_code=409, detail="Duvida ja finalizada.")
    return _duvida_dict(db, aprendizado.ignorar(db, duvida))


@router.get("/conhecimento", summary="Entradas da base de conhecimento")
def listar_conhecimento():
    entradas = conhecimento.carregar()
    return {
        "itens": [
            {"indice": indice, **entrada}
            for indice, entrada in enumerate(entradas)
        ],
        "total": len(entradas),
    }


@router.post(
    "/conhecimento",
    summary="Adicionar uma pergunta/resposta a base",
    status_code=201,
)
def adicionar_conhecimento(payload: EntradaConhecimento):
    try:
        entrada = conhecimento.adicionar(
            payload.pergunta, payload.resposta, payload.termos
        )
    except ValueError as erro:
        raise HTTPException(status_code=400, detail=str(erro)) from erro
    return entrada


@router.delete("/conhecimento/{indice}", summary="Remover uma entrada da base")
def remover_conhecimento(indice: int):
    if not conhecimento.remover(indice):
        raise HTTPException(status_code=404, detail="Entrada nao encontrada.")
    return {"removido": True}


@router.post("/conversas", summary="Iniciar conversa no simulador", status_code=201)
def criar(payload: ConversaCriar, db: Session = Depends(get_db)):
    conversa = motor.criar_conversa(
        db,
        contato=payload.contato,
        nome=payload.nome,
        canal=payload.canal,
    )
    return _detalhe(db, conversa)


@router.get("/conversas/{conversa_id}", summary="Detalhar conversa e mensagens")
def detalhar(conversa_id: int, db: Session = Depends(get_db)):
    return _detalhe(db, _buscar(db, conversa_id))


@router.post(
    "/conversas/{conversa_id}/mensagens",
    summary="Enviar mensagem como cliente (simulador)",
)
def enviar_como_cliente(
    conversa_id: int,
    payload: MensagemCliente,
    db: Session = Depends(get_db),
):
    conversa = _buscar(db, conversa_id)
    imagem = payload.imagem
    if imagem:
        if len(imagem) > LIMITE_IMAGEM:
            raise HTTPException(status_code=413, detail="Imagem muito grande.")
        if not re.match(r"^data:image/(png|jpe?g|webp|gif);base64,", imagem, re.IGNORECASE):
            raise HTTPException(
                status_code=400, detail="Envie a imagem como data URL (base64)."
            )
    try:
        novas = motor.processar_mensagem_cliente(
            db, conversa, texto=payload.texto, imagem=imagem
        )
    except ValueError as erro:
        raise HTTPException(status_code=409, detail=str(erro)) from erro
    # Simula o tempo de digitacao humana antes de "enviar" as respostas.
    if novas:
        pausas.esperar("".join(mensagem.texto or "" for mensagem in novas))
    db.refresh(conversa)
    return _detalhe(db, conversa)


@router.post("/conversas/{conversa_id}/assumir", summary="Assumir conversa")
def assumir(conversa_id: int, db: Session = Depends(get_db)):
    conversa = _buscar(db, conversa_id)
    try:
        motor.assumir_conversa(db, conversa)
    except ValueError as erro:
        raise HTTPException(status_code=409, detail=str(erro)) from erro
    db.refresh(conversa)
    return _detalhe(db, conversa)


@router.post("/conversas/{conversa_id}/responder", summary="Responder como humano")
def responder(
    conversa_id: int,
    payload: RespostaHumano,
    db: Session = Depends(get_db),
):
    conversa = _buscar(db, conversa_id)
    try:
        motor.responder_humano(db, conversa, payload.texto.strip())
    except ValueError as erro:
        raise HTTPException(status_code=409, detail=str(erro)) from erro
    db.refresh(conversa)
    return _detalhe(db, conversa)


@router.post("/conversas/{conversa_id}/devolver", summary="Devolver conversa para a IA")
def devolver(conversa_id: int, db: Session = Depends(get_db)):
    conversa = _buscar(db, conversa_id)
    try:
        motor.devolver_para_ia(db, conversa)
    except ValueError as erro:
        raise HTTPException(status_code=409, detail=str(erro)) from erro
    db.refresh(conversa)
    return _detalhe(db, conversa)


@router.post("/conversas/{conversa_id}/encerrar", summary="Encerrar conversa")
def encerrar(conversa_id: int, db: Session = Depends(get_db)):
    conversa = _buscar(db, conversa_id)
    motor.encerrar_conversa(db, conversa)
    db.refresh(conversa)
    return _detalhe(db, conversa)
