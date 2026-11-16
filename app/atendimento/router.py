from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Conversa, Duvida, MensagemAtendimento, ResultadoAtendimento
from ..security import verificar_api_key
from . import (
    aplicativos,
    aprendizado,
    config,
    conhecimento,
    historico,
    ia,
    motor,
    pausas,
)
from .schemas import (
    ConversaCriar,
    EntradaConhecimento,
    HistoricoAnalise,
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
# Indicadores comerciais
# ---------------------------------------------------------------------------
def _periodo(
    periodo: str,
    inicio: str | None,
    fim: str | None,
) -> tuple[datetime, datetime, str]:
    hoje = datetime.now(timezone.utc).date()

    if periodo == "hoje":
        data_inicio = hoje
        data_fim = hoje
        rotulo = "Hoje"
    elif periodo == "7d":
        data_inicio = hoje - timedelta(days=6)
        data_fim = hoje
        rotulo = "Últimos 7 dias"
    elif periodo == "mes":
        data_inicio = hoje.replace(day=1)
        data_fim = hoje
        rotulo = "Este mês"
    elif periodo == "personalizado":
        if not inicio or not fim:
            raise HTTPException(
                status_code=400,
                detail="Informe as datas inicio e fim para o periodo personalizado.",
            )
        try:
            data_inicio = date.fromisoformat(inicio)
            data_fim = date.fromisoformat(fim)
        except ValueError as erro:
            raise HTTPException(
                status_code=400,
                detail="Use datas no formato AAAA-MM-DD.",
            ) from erro
        if data_inicio > data_fim:
            raise HTTPException(
                status_code=400,
                detail="A data inicial deve ser anterior ou igual à final.",
            )
        rotulo = "Período personalizado"
    else:
        raise HTTPException(status_code=400, detail="Periodo invalido.")

    inicio_dt = datetime.combine(data_inicio, datetime.min.time(), tzinfo=timezone.utc)
    fim_dt = datetime.combine(data_fim + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc)
    return inicio_dt, fim_dt, rotulo


def _resultado_dict(resultado: ResultadoAtendimento, conversa: Conversa | None = None) -> dict:
    return {
        "id": resultado.id,
        "conversa_id": resultado.conversa_id,
        "contato": resultado.contato,
        "nome": conversa.nome if conversa else None,
        "canal": conversa.canal if conversa else None,
        "tipo": resultado.tipo,
        "status": resultado.status,
        "origem": resultado.origem,
        "observacao": resultado.observacao,
        "criado_em": _iso(resultado.criado_em),
    }


@router.get("/indicadores", summary="Indicadores comerciais do atendimento")
def indicadores(
    periodo: str = Query(default="hoje"),
    inicio: str | None = Query(default=None),
    fim: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    inicio_dt, fim_dt, rotulo = _periodo(periodo, inicio, fim)

    contatos_unicos = db.scalar(
        select(func.count(func.distinct(Conversa.contato))).where(
            Conversa.canal != "simulador",
            Conversa.ultima_mensagem_em >= inicio_dt,
            Conversa.ultima_mensagem_em < fim_dt,
        )
    ) or 0

    contratacoes = db.scalar(
        select(func.count(ResultadoAtendimento.id)).where(
            ResultadoAtendimento.tipo == "contratacao",
            ResultadoAtendimento.status == "confirmado",
            ResultadoAtendimento.criado_em >= inicio_dt,
            ResultadoAtendimento.criado_em < fim_dt,
            Conversa.canal != "simulador",
        ).join(Conversa, ResultadoAtendimento.conversa_id == Conversa.id, isouter=True)
    ) or 0

    renovacoes = db.scalar(
        select(func.count(ResultadoAtendimento.id)).where(
            ResultadoAtendimento.tipo == "renovacao",
            ResultadoAtendimento.status == "confirmado",
            ResultadoAtendimento.criado_em >= inicio_dt,
            ResultadoAtendimento.criado_em < fim_dt,
            Conversa.canal != "simulador",
        ).join(Conversa, ResultadoAtendimento.conversa_id == Conversa.id, isouter=True)
    ) or 0

    resultados = db.execute(
        select(ResultadoAtendimento, Conversa)
        .join(Conversa, ResultadoAtendimento.conversa_id == Conversa.id, isouter=True)
        .where(
            ResultadoAtendimento.status == "confirmado",
            ResultadoAtendimento.criado_em >= inicio_dt,
            ResultadoAtendimento.criado_em < fim_dt,
            Conversa.canal != "simulador",
        )
        .order_by(ResultadoAtendimento.criado_em.desc())
    ).all()

    return {
        "periodo": periodo,
        "rotulo": rotulo,
        "inicio": _iso(inicio_dt),
        "fim": _iso(fim_dt),
        "contatos_unicos": contatos_unicos,
        "contratacoes_confirmadas": contratacoes,
        "renovacoes_confirmadas": renovacoes,
        "total_resultados": contratacoes + renovacoes,
        "itens": [
            _resultado_dict(resultado, conversa)
            for resultado, conversa in resultados
        ],
    }


class ResultadoCriar(BaseModel):
    conversa_id: int
    tipo: str
    observacao: str | None = None


@router.post("/resultados", summary="Registrar contratacao ou renovacao confirmada", status_code=201)
def registrar_resultado(payload: ResultadoCriar, db: Session = Depends(get_db)):
    tipo = payload.tipo.strip().lower()
    if tipo not in {"contratacao", "renovacao"}:
        raise HTTPException(
            status_code=400,
            detail="Tipo deve ser contratacao ou renovacao.",
        )

    conversa = _buscar(db, payload.conversa_id)
    if conversa.canal == "simulador":
        raise HTTPException(
            status_code=400,
            detail="Conversas do simulador nao entram nos indicadores.",
        )

    existente = db.scalar(
        select(ResultadoAtendimento).where(
            ResultadoAtendimento.conversa_id == conversa.id,
            ResultadoAtendimento.tipo == tipo,
            ResultadoAtendimento.status == "confirmado",
        )
    )
    if existente:
        raise HTTPException(
            status_code=409,
            detail=f"Este contato ja possui {tipo} confirmada neste periodo.",
        )

    resultado = ResultadoAtendimento(
        conversa_id=conversa.id,
        contato=conversa.contato,
        tipo=tipo,
        status="confirmado",
        origem="manual",
        observacao=(payload.observacao or "").strip() or None,
    )
    db.add(resultado)
    db.commit()
    db.refresh(resultado)
    return _resultado_dict(resultado, conversa)


@router.get("/resultados", summary="Listar resultados confirmados")
def listar_resultados(
    periodo: str = Query(default="hoje"),
    inicio: str | None = Query(default=None),
    fim: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    inicio_dt, fim_dt, _ = _periodo(periodo, inicio, fim)
    resultados = db.execute(
        select(ResultadoAtendimento, Conversa)
        .join(Conversa, ResultadoAtendimento.conversa_id == Conversa.id, isouter=True)
        .where(
            ResultadoAtendimento.status == "confirmado",
            ResultadoAtendimento.criado_em >= inicio_dt,
            ResultadoAtendimento.criado_em < fim_dt,
            Conversa.canal != "simulador",
        )
        .order_by(ResultadoAtendimento.criado_em.desc())
    ).all()
    return {
        "itens": [
            _resultado_dict(resultado, conversa)
            for resultado, conversa in resultados
        ],
        "total": len(resultados),
    }


@router.delete("/resultados/{resultado_id}", summary="Remover um resultado confirmado")
def remover_resultado(resultado_id: int, db: Session = Depends(get_db)):
    resultado = db.get(ResultadoAtendimento, resultado_id)
    if not resultado:
        raise HTTPException(status_code=404, detail="Resultado nao encontrado.")
    db.delete(resultado)
    db.commit()
    return {"removido": True}


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
        duvida, enviado = aprendizado.responder(
            db,
            duvida,
            payload.resposta,
            salvar_na_base=payload.salvar_na_base,
            enviar_ao_cliente=payload.enviar_ao_cliente,
        )
    except ValueError as erro:
        raise HTTPException(status_code=400, detail=str(erro)) from erro
    return {**_duvida_dict(db, duvida), "enviado_ao_cliente": enviado}


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


@router.post(
    "/historico/analisar",
    summary="Ler um historico do WhatsApp e sugerir perguntas e respostas",
)
def analisar_historico(payload: HistoricoAnalise):
    """Extrai pares pergunta/resposta do arquivo .txt exportado do WhatsApp.

    A resposta e uma lista de candidatos. O atendente revisa, marca os bons e
    salva na base de conhecimento pelo endpoint /atendimento/conhecimento.
    """
    return historico.analisar(
        payload.texto, negocio=payload.negocio, limite=payload.limite
    )


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
