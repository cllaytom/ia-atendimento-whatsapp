"""Regras de negocio da campanha: quem entra, o que seria enviado e quando."""

from __future__ import annotations

import hashlib
from collections import Counter
from datetime import date, timedelta

from . import armazenamento, config, mensagens, parametros, selecao
from .contatos import normalizar, primeiro_nome
from .planilha import data_iso


def numero_remetente() -> str:
    """Numero salvo na tela; se nao houver, usa o padrao de configuracao."""
    return armazenamento.numero_remetente_salvo() or config.numero_remetente()


def numero_teste() -> str:
    """Numero de teste salvo na tela; se nao houver, usa o padrao."""
    return armazenamento.numero_teste_salvo() or config.numero_teste()


def _resumo_vazio() -> dict:
    return {
        "lidos": 0,
        "sem_telefone": 0,
        "optout": 0,
        "repetido": 0,
        "em_cooldown": 0,
        "ja_na_fila": 0,
        "remetente": 0,
        "teste": 0,
        "compartilhado": 0,
        "elegiveis": 0,
    }


def elegiveis(
    produto: str | None = None,
    limite: int | None = None,
    hoje: date | None = None,
    apenas_unicos: bool = False,
) -> dict:
    """Lista quem pode receber, com o motivo de cada exclusao contabilizado."""
    resumo = _resumo_vazio()
    try:
        candidatos = selecao.coletar(produto=produto, hoje=hoje)
    except selecao.BaseIndisponivel as erro:
        return {"disponivel": False, "erro": str(erro), "itens": [], "resumo": resumo, "total": 0}

    bloqueados = armazenamento.optouts()
    cooldown = armazenamento.telefones_em_cooldown(parametros.atuais()["cooldown_dias"])
    na_fila = armazenamento.telefones_na_fila()
    remetente = numero_remetente()
    numero_de_teste = numero_teste()
    contagem = Counter(c["telefone"] for c in candidatos if c.get("telefone"))

    vistos: set[str] = set()
    itens: list[dict] = []
    for candidato in candidatos:
        resumo["lidos"] += 1
        telefone = candidato.get("telefone")
        if not telefone:
            resumo["sem_telefone"] += 1
            continue
        if telefone in vistos:
            resumo["repetido"] += 1
            continue
        vistos.add(telefone)
        if apenas_unicos and contagem[telefone] > 1:
            resumo["compartilhado"] += 1
            continue
        if telefone in bloqueados:
            resumo["optout"] += 1
            continue
        if remetente and telefone == remetente:
            resumo["remetente"] += 1
            continue
        if numero_de_teste and telefone == numero_de_teste:
            resumo["teste"] += 1
            continue
        if telefone in cooldown:
            resumo["em_cooldown"] += 1
            continue
        if telefone in na_fila:
            resumo["ja_na_fila"] += 1
            continue
        resumo["elegiveis"] += 1
        itens.append(candidato)

    total = resumo["elegiveis"]
    if limite:
        itens = itens[:limite]
    return {"disponivel": True, "erro": None, "itens": itens, "resumo": resumo, "total": total}


def _modelo(indice: int, modelo: str | None, variar: bool) -> str:
    if variar:
        return mensagens.VARIANTES[indice % len(mensagens.VARIANTES)]
    return (modelo or mensagens.PADRAO).strip()


def previa(
    modelo: str | None = None,
    produto: str | None = None,
    limite: int = config.LIMITE_PREVIA,
    variar: bool = True,
    apenas_unicos: bool = False,
) -> dict:
    """Monta as mensagens exatamente como sairiam, sem gravar nada."""
    base = elegiveis(produto=produto, limite=limite, apenas_unicos=apenas_unicos)
    if not base["disponivel"]:
        return base
    itens = []
    for indice, candidato in enumerate(base["itens"]):
        usado = _modelo(indice, modelo, variar)
        texto = mensagens.renderizar(usado, candidato.get("nome"), candidato.get("usuario"))
        itens.append(
            {
                "id": candidato["id"],
                "nome": candidato.get("nome"),
                "primeiro_nome": candidato.get("primeiro_nome"),
                "telefone": candidato.get("telefone"),
                "produto": candidato.get("produto"),
                "vencimento": candidato.get("vencimento"),
                "variante": indice % len(mensagens.VARIANTES) + 1 if variar else 1,
                "texto": texto,
                "caracteres": len(texto),
            }
        )
    return {
        "disponivel": True,
        "erro": None,
        "resumo": base["resumo"],
        "total": base["total"],
        "itens": itens,
    }


def criar_fila(
    modelo: str | None = None,
    produto: str | None = None,
    limite: int = config.LIMITE_FILA,
    variar: bool = True,
    apenas_unicos: bool = False,
) -> dict:
    """Grava os alvos escolhidos no banco da campanha (nada e enviado)."""
    base = elegiveis(produto=produto, limite=None, apenas_unicos=apenas_unicos)
    if not base["disponivel"]:
        return {
            "disponivel": False,
            "erro": base["erro"],
            "resumo": base["resumo"],
            "criados": 0,
            "total": 0,
        }
    escolhidos = base["itens"][:limite]
    para_gravar = []
    for indice, candidato in enumerate(escolhidos):
        usado = _modelo(indice, modelo, variar)
        para_gravar.append(
            {
                **candidato,
                "texto": mensagens.renderizar(
                    usado, candidato.get("nome"), candidato.get("usuario")
                ),
            }
        )
    criados = armazenamento.adicionar_alvos(para_gravar)
    return {
        "disponivel": True,
        "erro": None,
        "resumo": base["resumo"],
        "criados": criados,
        "total": len(para_gravar),
    }


def _id_manual(telefone: str) -> int:
    """assinatura_id sintetico (negativo) para numero que nao vem da base.

    Negativo para nunca colidir com o id real da base de assinaturas e estavel
    para o mesmo telefone (repetir a lista nao duplica o alvo).
    """
    resumo = hashlib.sha1(telefone.encode("utf-8")).hexdigest()[:12]
    return -int(resumo, 16)


def _campos_da_linha(linha: str) -> list[str]:
    """Separa 'telefone;nome;produto;vencimento' por ; tab ou virgula."""
    for separador in (";", "\t", ","):
        if separador in linha:
            return [parte.strip() for parte in linha.split(separador)]
    return [linha.strip()]


def _analisar_numeros(
    linhas: str,
    modelo: str | None = None,
    produto: str | None = None,
    vencimento: str | None = None,
) -> tuple[list[dict], list[dict]]:
    """Separa a lista em (o que entra, o que fica de fora e por que)."""
    na_fila = armazenamento.telefones_na_fila()
    conhecidos = armazenamento.telefones_registrados()
    bloqueados = armazenamento.optouts()
    cooldown = armazenamento.telefones_em_cooldown(parametros.atuais()["cooldown_dias"])
    remetente = numero_remetente()
    teste = numero_teste()

    ignorados: list[dict] = []
    vistos: set[str] = set()
    para_gravar: list[dict] = []

    for bruto in (linhas or "").splitlines():
        if not bruto.strip():
            continue
        partes = _campos_da_linha(bruto)
        telefone = normalizar(partes[0])
        nome = partes[1] if len(partes) > 1 and partes[1] else None
        item_produto = partes[2] if len(partes) > 2 and partes[2] else produto
        bruto_vencimento = (
            partes[3] if len(partes) > 3 and partes[3] else (vencimento or "")
        )
        item_vencimento = data_iso(bruto_vencimento) or None

        if not telefone:
            ignorados.append({"linha": bruto.strip()[:60], "motivo": "telefone invalido"})
            continue
        if len(telefone) != 13:
            ignorados.append(
                {"telefone": telefone, "motivo": "12 digitos: confira o 9o digito"}
            )
            continue
        if telefone in vistos:
            ignorados.append({"telefone": telefone, "motivo": "repetido na lista"})
            continue
        vistos.add(telefone)

        if telefone == remetente:
            ignorados.append({"telefone": telefone, "motivo": "e o proprio remetente"})
            continue
        if telefone == teste:
            ignorados.append({"telefone": telefone, "motivo": "e o numero de teste"})
            continue
        if telefone in bloqueados:
            ignorados.append({"telefone": telefone, "motivo": "pediu para sair (opt-out)"})
            continue
        if telefone in cooldown:
            ignorados.append({"telefone": telefone, "motivo": "em cooldown (ja recebeu)"})
            continue
        if telefone in na_fila:
            ignorados.append({"telefone": telefone, "motivo": "ja esta na fila"})
            continue
        if telefone in conhecidos:
            ignorados.append(
                {"telefone": telefone, "motivo": "ja passou pela campanha (falha/enviado)"}
            )
            continue

        para_gravar.append(
            {
                "id": _id_manual(telefone),
                "telefone": telefone,
                "nome": nome,
                "primeiro_nome": primeiro_nome(nome),
                "produto": item_produto,
                "vencimento": item_vencimento,
                "texto": mensagens.renderizar(modelo or mensagens.PADRAO, nome),
            }
        )

    return para_gravar, ignorados


def visualizar_numeros(
    linhas: str,
    modelo: str | None = None,
    produto: str | None = None,
    vencimento: str | None = None,
    amostra: int = 20,
) -> dict:
    """Confere a lista SEM gravar: mostra o que entraria e o que fica fora."""
    para_gravar, ignorados = _analisar_numeros(linhas, modelo, produto, vencimento)
    return {
        "novos": [
            {
                "telefone": item["telefone"],
                "nome": item["nome"],
                "produto": item["produto"],
                "vencimento": item["vencimento"],
            }
            for item in para_gravar[:amostra]
        ],
        "total_novos": len(para_gravar),
        "ignorados": ignorados[:amostra],
        "total_ignorados": len(ignorados),
    }


def adicionar_numeros(
    linhas: str,
    modelo: str | None = None,
    produto: str | None = None,
    vencimento: str | None = None,
) -> dict:
    """Grava uma lista propria de numeros na fila (nada e enviado).

    Cada linha aceita: telefone, telefone;nome, telefone;nome;produto ou
    telefone;nome;produto;vencimento. Aplica as mesmas guardas da campanha
    (remetente, teste, opt-out, cooldown, ja na fila) e recusa numeros de
    12 digitos, que costumam falhar por falta do 9o digito.
    """
    para_gravar, ignorados = _analisar_numeros(linhas, modelo, produto, vencimento)
    criados = armazenamento.adicionar_alvos(para_gravar)
    return {
        "adicionados": criados,
        "considerados": len(para_gravar),
        "ignorados": ignorados,
    }


def compartilhados(minimo: int = 2) -> list[dict]:
    """Numeros usados por mais de um cadastro (para revisao manual)."""
    candidatos = selecao.coletar()
    grupos: dict[str, list[dict]] = {}
    for candidato in candidatos:
        telefone = candidato.get("telefone")
        if not telefone:
            continue
        grupos.setdefault(telefone, []).append(
            {
                "id": candidato["id"],
                "nome": candidato.get("nome"),
                "status": candidato.get("status"),
                "vencimento": candidato.get("vencimento"),
            }
        )
    itens = [
        {
            "telefone": telefone,
            "total": len(clientes),
            "clientes": sorted(clientes, key=lambda c: (c.get("nome") or "").lower()),
        }
        for telefone, clientes in grupos.items()
        if len(clientes) >= minimo
    ]
    itens.sort(key=lambda grupo: (-grupo["total"], grupo["telefone"]))
    return itens


def _dia_util(primeiro: date) -> date:
    dia = primeiro
    while dia.weekday() not in config.DIAS_SEMANA:
        dia += timedelta(days=1)
    return dia


def plano(hoje: date | None = None) -> dict:
    """Distribui a fila pendente nos dias uteis seguindo a rampa (10/20/30)."""
    pendentes = armazenamento.fila("pendente")
    if not pendentes:
        return {"dias": [], "total": 0, "estimativa": "fila vazia"}

    valores = parametros.atuais()
    fixa = valores["cota_diaria"]
    janelas = (
        [f"{inicio}–{fim}" for inicio, fim in config.JANELAS]
        if valores["respeitar_janelas"]
        else ["manual (qualquer horário)"]
    )

    restante = len(pendentes)
    dia = _dia_util((hoje or date.today()) + timedelta(days=1))
    indice = 0
    dias = []
    while restante > 0:
        limite = fixa if fixa > 0 else config.RAMPA[min(indice, len(config.RAMPA) - 1)]
        quantidade = min(limite, restante)
        dias.append(
            {
                "data": dia.isoformat(),
                "quantidade": quantidade,
                "janelas": janelas,
            }
        )
        restante -= quantidade
        indice += 1
        dia = _dia_util(dia + timedelta(days=1))
        if len(dias) > 400:  # protecao contra laco infinito
            break

    return {
        "dias": dias,
        "total": len(pendentes),
        "estimativa": f"{len(pendentes)} contatos em {len(dias)} dia(s) util(eis)",
    }
