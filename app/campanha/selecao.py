"""Selecao dos clientes inativos, lendo a base de assinaturas SEM escrita."""

from __future__ import annotations

import sqlite3
from datetime import date

from . import config
from .contatos import normalizar, primeiro_nome

CAMPOS = "id, nome, usuario, contato, status, vencimento, produto, plano_nome, valor_final"

CONDICAO_ELEGIVEL = (
    "(upper(coalesce(status,'')) IN ('INATIVO','SUSPENSO') "
    " OR (upper(coalesce(status,'')) NOT IN ('CANCELADO','ATIVO','TESTE') "
    "     AND vencimento IS NOT NULL AND vencimento < ?))"
)


class BaseIndisponivel(RuntimeError):
    """Base de assinaturas ausente ou ilegivel."""


def _conectar() -> sqlite3.Connection:
    if not config.BANCO_ASSINATURAS.exists():
        raise BaseIndisponivel(
            "Base de assinaturas nao encontrada em " + str(config.BANCO_ASSINATURAS)
        )
    uri = "file:" + config.BANCO_ASSINATURAS.as_posix() + "?mode=ro"
    try:
        con = sqlite3.connect(uri, uri=True, timeout=5)
    except sqlite3.Error as erro:  # pragma: no cover - depende do arquivo real
        raise BaseIndisponivel("Falha ao abrir a base somente leitura: " + str(erro)) from erro
    con.row_factory = sqlite3.Row
    return con


def coletar(produto: str | None = None, hoje: date | None = None) -> list[dict]:
    """Clientes inativos/suspensos ou vencidos, exceto cancelados/ativos/teste."""
    hoje = hoje or date.today()
    sql = "SELECT " + CAMPOS + " FROM assinaturas WHERE " + CONDICAO_ELEGIVEL
    parametros: list = [hoje.isoformat()]
    if produto:
        sql += " AND lower(coalesce(produto,'')) = lower(?)"
        parametros.append(produto.strip())
    sql += " ORDER BY vencimento ASC, id ASC"

    con = _conectar()
    try:
        linhas = con.execute(sql, parametros).fetchall()
    finally:
        con.close()

    itens = []
    for linha in linhas:
        item = dict(linha)
        item["telefone"] = normalizar(item.get("contato"))
        item["primeiro_nome"] = primeiro_nome(item.get("nome"), item.get("usuario"))
        itens.append(item)
    return itens


def produtos() -> list[dict]:
    """Produtos com clientes (para o filtro da tela)."""
    con = _conectar()
    try:
        linhas = con.execute(
            "SELECT coalesce(nullif(trim(produto),''),'Sem produto') AS produto, "
            "count(*) AS total FROM assinaturas "
            "WHERE upper(coalesce(status,'')) NOT IN ('CANCELADO') "
            "GROUP BY 1 ORDER BY total DESC, produto ASC"
        ).fetchall()
    finally:
        con.close()
    return [dict(linha) for linha in linhas]
