from datetime import date
import calendar

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from .database import get_db
from .models import Assinatura, Lancamento
from .schemas import AssinaturaResumo
from .security import verificar_api_key


router = APIRouter(
    prefix="/clientes",
    dependencies=[Depends(verificar_api_key)],
)


@router.get("/resumo-filtrado")
def resumo(
    mes: str,
    situacao: str = "em_dia",
    filtrar_vencimento: bool = False,
    produto: str = "todos",
    db: Session = Depends(get_db),
):
    try:
        ano, numero = map(int, mes.split("-"))
        inicio = date(ano, numero, 1)
        fim = date(ano, numero, calendar.monthrange(ano, numero)[1])
    except (ValueError, TypeError):
        raise HTTPException(422, "Mes invalido. Use AAAA-MM.")

    situacoes_validas = (
        "em_dia",
        "vencidos",
        "teste",
        "inativos",
        "cancelados",
        "sem_vencimento",
        "todos",
    )
    if situacao not in situacoes_validas:
        raise HTTPException(422, "Situacao invalida.")

    produto = produto.strip().upper()
    if produto not in ("TODOS", "IPTV", "INTERNET"):
        raise HTTPException(422, "Produto invalido.")

    hoje = date.today()
    stmt = select(Assinatura)

    if produto != "TODOS":
        stmt = stmt.where(
            func.upper(func.trim(Assinatura.produto)) == produto
        )

    if situacao == "em_dia":
        stmt = stmt.where(
            Assinatura.status == "ATIVO",
            Assinatura.vencimento >= hoje,
        )
    elif situacao == "vencidos":
        stmt = stmt.where(
            Assinatura.status == "ATIVO",
            Assinatura.vencimento < hoje,
        )
    elif situacao == "teste":
        stmt = stmt.where(Assinatura.status == "TESTE")
    elif situacao == "inativos":
        stmt = stmt.where(
            Assinatura.status.in_(["INATIVO", "SUSPENSO"])
        )
    elif situacao == "cancelados":
        stmt = stmt.where(Assinatura.status == "CANCELADO")
    elif situacao == "sem_vencimento":
        stmt = stmt.where(Assinatura.vencimento.is_(None))

    if filtrar_vencimento:
        stmt = stmt.where(
            Assinatura.vencimento.between(inicio, fim)
        )

    itens = db.scalars(
        stmt.order_by(Assinatura.vencimento, Assinatura.id)
    ).all()

    total_base = len(
        db.scalars(select(Assinatura.id)).all()
    )

    ativos = [
        a for a in itens
        if a.status == "ATIVO"
        and a.vencimento
        and a.vencimento >= hoje
    ]
    vencidos = [
        a for a in itens
        if a.status == "ATIVO"
        and a.vencimento
        and a.vencimento < hoje
    ]
    proximos = [
        a for a in ativos
        if 0 <= (a.vencimento - hoje).days <= 30
    ]

    lancamentos = db.scalars(
        select(Lancamento).where(
            Lancamento.data.between(inicio, fim)
        )
    ).all()

    recebido = sum(
        a.valor or 0
        for a in lancamentos
        if a.tipo in ("renovacao", "pagamento")
    )
    despesas = sum(
        a.valor or 0
        for a in lancamentos
        if a.tipo == "despesa"
    )

    por_produto = {}
    por_plano = {}

    for a in itens:
        nome_produto = a.produto or "SEM PRODUTO"
        por_produto[nome_produto] = (
            por_produto.get(nome_produto, 0) + 1
        )

        nome_plano = a.plano_nome or "SEM PLANO"
        por_plano[nome_plano] = (
            por_plano.get(nome_plano, 0) + 1
        )

    return {
        "hoje": hoje,
        "mes": mes,
        "total": len(itens),
        "total_base": total_base,
        "ativas": len(ativos),
        "vencidas_por_data": len(vencidos),
        "vencendo_7_dias": sum(
            0 <= (a.vencimento - hoje).days <= 7
            for a in ativos
        ),
        "inativas": sum(a.status == "INATIVO" for a in itens),
        "suspensas": sum(a.status == "SUSPENSO" for a in itens),
        "canceladas": sum(a.status == "CANCELADO" for a in itens),
        "valor_carteira": round(
            sum(a.valor_final or 0 for a in itens), 2
        ),
        "mrr": round(
            sum(a.valor_final or 0 for a in ativos), 2
        ),
        "recebido_mes": round(recebido, 2),
        "despesas_mes": round(despesas, 2),
        "lucro_mes": round(recebido - despesas, 2),
        "por_produto": por_produto,
        "por_plano": por_plano,
        "clientes": [
            AssinaturaResumo.model_validate(a).model_dump(mode="json")
            for a in itens
        ],
                "proximos": [
            {
                "id": a.id,
                "nome": a.nome,
                "contato": a.contato,
                "plano": a.plano_nome,
                "valor_final": a.valor_final,
                "vencimento": a.vencimento,
            }
            for a in proximos
        ],
    }