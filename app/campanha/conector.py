"""Cerebro do envio automatico (fase 2).

O worker Node nao decide nada: ele pergunta aqui se pode falar, qual e o
proximo alvo e quanto esperar antes do proximo. Enquanto
config.ENVIO_REAL_HABILITADO for False, nenhum alvo sai da fila: `reservar`
levanta Bloqueado e o router responde 409.

Regras aplicadas neste modulo (e nao no worker):
- trava de seguranca + modo "real" + campanha ativa;
- janela de horario e dia da semana;
- rampa de aquecimento 10 -> 20 -> 30 por dia;
- intervalo humano entre envios e pausa longa a cada N;
- opt-out, cooldown e numero remetente sempre fora da fila;
- reserva com validade (se o worker morrer, o alvo volta sozinho).
"""

from __future__ import annotations

from datetime import datetime, timedelta

from . import armazenamento, config, humanizacao, parametros

FORMATO = "%Y-%m-%d %H:%M:%S"
SITUACOES = (*config.SITUACOES_ENVIADO, "falha")


class Bloqueado(Exception):
    """Nada pode ser reservado agora. `esperar` sugere quando tentar de novo."""

    def __init__(self, motivo: str, esperar: int = 0):
        super().__init__(motivo)
        self.motivo = motivo
        self.esperar = int(esperar)


def _agora(momento: datetime | None = None) -> datetime:
    return momento or datetime.now()


def _parse(valor: str | None) -> datetime | None:
    try:
        return datetime.strptime(valor or "", FORMATO)
    except ValueError:
        return None


def _minutos(hhmm: str) -> int:
    try:
        hora, minuto = hhmm.split(":")
        return int(hora) * 60 + int(minuto)
    except (AttributeError, ValueError):
        return -1


def dentro_da_janela(agora: datetime) -> tuple[bool, str | None]:
    """Seg-sex, dentro de uma das janelas. Em modo manual, sempre liberado."""
    if not parametros.atuais()["respeitar_janelas"]:
        return True, "manual (sem janela de horario)"
    if agora.weekday() not in config.DIAS_SEMANA:
        return False, None
    minuto_agora = agora.hour * 60 + agora.minute
    for inicio, fim in config.JANELAS:
        if _minutos(inicio) <= minuto_agora <= _minutos(fim):
            return True, f"{inicio} a {fim}"
    return False, None


def cota_do_dia(agora: datetime) -> int:
    """Cota fixa do painel ou, se 0, a rampa 10 -> 20 -> 30."""
    ajuste = parametros.atuais()["cota_diaria"]
    if ajuste > 0:
        return ajuste
    hoje = agora.strftime("%Y-%m-%d")
    anteriores = {dia for dia in armazenamento.dias_com_envio() if dia < hoje}
    indice = min(len(anteriores), len(config.RAMPA) - 1)
    return config.RAMPA[indice]


def _espera(agora: datetime) -> int:
    proximo = _parse(armazenamento.proximo_envio_em())
    if not proximo:
        return 0
    return max(0, int((proximo - agora).total_seconds()))


def _remetente() -> str:
    return armazenamento.numero_remetente_salvo() or config.numero_remetente()


def _teste() -> str:
    return armazenamento.numero_teste_salvo() or config.numero_teste()


def _erro_sem_whatsapp(erro: str | None) -> bool:
    """Numero que nao existe no WhatsApp: nao e instabilidade, nao pausa."""
    return "sem whatsapp" in (erro or "").strip().lower()


def _avaliar(agora: datetime) -> tuple[bool, str, int]:
    if not config.ENVIO_REAL_HABILITADO:
        return False, "trava de seguranca ativa: envio real desligado no codigo", 0

    modo = config.MODO if config.MODO in config.MODOS_VALIDOS else "previa"
    if modo != config.MODO_REAL:
        return False, f"modo {modo}: nenhum canal de envio real", 0

    if not armazenamento.campanha_ativa():
        motivo = armazenamento.motivo_pausa()
        return False, "campanha desligada" + (f" ({motivo})" if motivo else ""), 0

    dentro, _ = dentro_da_janela(agora)
    if not dentro:
        return False, "fora da janela de envio (seg-sex 09:00-11:30 e 14:00-17:30)", 0


    enviados = armazenamento.envios_do_dia(agora.strftime("%Y-%m-%d"))
    cota = cota_do_dia(agora)
    if enviados >= cota:
        return False, f"cota do dia atingida ({enviados}/{cota})", 0

    esperar = _espera(agora)
    if esperar > 0:
        return False, f"aguardando intervalo entre envios ({esperar}s)", esperar

    if not armazenamento.fila("pendente"):
        return False, "fila vazia", 0

    return True, "liberado", 0


def _avaliar_manual(agora: datetime) -> tuple[bool, str]:
    """Modo manual: o atendente decide. Ignora janela, cota e intervalo."""
    if not config.ENVIO_REAL_HABILITADO:
        return False, "trava de seguranca ativa: envio real desligado no codigo"

    modo = config.MODO if config.MODO in config.MODOS_VALIDOS else "previa"
    if modo != config.MODO_REAL:
        return False, f"modo {modo}: nenhum canal de envio real"

    if not armazenamento.campanha_ativa():
        motivo = armazenamento.motivo_pausa()
        return False, "campanha desligada" + (f" ({motivo})" if motivo else "")

    return True, "liberado (manual)"


def estado(momento: datetime | None = None) -> dict:
    """Retrato do que o worker pode fazer agora."""
    agora = _agora(momento)
    hoje = agora.strftime("%Y-%m-%d")
    enviados = armazenamento.envios_do_dia(hoje)
    cota = cota_do_dia(agora)
    dentro, janela = dentro_da_janela(agora)
    liberado, motivo, esperar = _avaliar(agora)
    valores = parametros.atuais()

    return {
        "agora": agora.strftime(FORMATO),
        "liberado": liberado,
        "motivo": motivo,
        "trava": not config.ENVIO_REAL_HABILITADO,
        "modo": config.MODO,
        "ativa": armazenamento.campanha_ativa(),
        "dentro_da_janela": dentro,
        "janela_atual": janela,
        "janelas_ativas": valores["respeitar_janelas"],
        "janelas": [f"{inicio} a {fim}" for inicio, fim in config.JANELAS],
        "dias_semana": list(config.DIAS_SEMANA),
        "enviados_hoje": enviados,
        "cota_dia": cota,
        "cota_fixa": valores["cota_diaria"],
        "restante_hoje": max(0, cota - enviados),
        "pendentes": len(armazenamento.fila("pendente")),
        "reservados": len(armazenamento.fila("enviando")),
        "esperar_segundos": esperar,
        "proximo_envio_em": armazenamento.proximo_envio_em(),
        "intervalo": [valores["intervalo_min"], valores["intervalo_max"]],
        "pausa_cada": valores["pausa_cada"],
        "pausa": [valores["pausa_min"], valores["pausa_max"]],
        "cooldown_dias": valores["cooldown_dias"],
        "max_tentativas": valores["max_tentativas"],
        "falhas_consecutivas": armazenamento.falhas_consecutivas(),
        "max_falhas_seguidas": valores["max_falhas_seguidas"],
        "ultimo_erro": armazenamento.ultimo_erro(),
        "ultimo_erro_em": armazenamento.ultimo_erro_em(),
        "erros_worker": armazenamento.erros_worker(),
        "reserva_minutos": config.CONECTOR_RESERVA_MINUTOS,
        "worker": armazenamento.worker_status(),
        "numero_remetente": _remetente(),
        "numero_teste": _teste(),
        "envio_real_habilitado": config.ENVIO_REAL_HABILITADO,
    }


def reservar(momento: datetime | None = None) -> dict:
    """Reserva o proximo alvo (status 'enviando') e devolve o que enviar."""
    agora = _agora(momento)
    armazenamento.liberar_reservas_expiradas()

    liberado, motivo, esperar = _avaliar(agora)
    if not liberado:
        raise Bloqueado(motivo, esperar)

    bloqueados = armazenamento.optouts()
    cooldown = armazenamento.telefones_em_cooldown(parametros.atuais()["cooldown_dias"])
    proprio = _remetente()

    for item in armazenamento.fila("pendente"):
        telefone = item["telefone"]
        if telefone in bloqueados or telefone in cooldown or telefone == proprio:
            armazenamento.cancelar_alvo(item["id"])
            continue
        if not armazenamento.marcar_enviando(item["id"]):
            continue
        return {
            "alvo_id": item["id"],
            "telefone": telefone,
            "nome": item.get("nome"),
            "primeiro_nome": item.get("primeiro_nome"),
            "texto": item["texto"],
            "vencimento": item.get("vencimento"),
            "reservado_em": agora.strftime(FORMATO),
            "validade_minutos": config.CONECTOR_RESERVA_MINUTOS,
            "digitacao_segundos": humanizacao.calcular(item["texto"]),
            "esperar_segundos": 0,
        }

    raise Bloqueado("nenhum alvo valido na fila (bloqueados, cooldown ou o proprio numero)", 0)


def reservar_manual(momento: datetime | None = None) -> dict | None:
    """Reserva o alvo de um pedido feito no painel (worker --manual).

    Devolve None quando nao ha pedido: o worker apenas espera. Cota, janela e
    intervalo nao valem aqui: quem decide o ritmo e o atendente.
    """
    agora = _agora(momento)
    armazenamento.liberar_reservas_expiradas()

    liberado, motivo = _avaliar_manual(agora)
    if not liberado:
        raise Bloqueado(motivo, 0)

    pedido = armazenamento.proximo_pedido()
    if not pedido:
        return None

    item = armazenamento.alvo(pedido["alvo_id"])
    if not item or item["status"] != "pendente":
        armazenamento.cancelar_pedido(pedido["alvo_id"])
        return None

    telefone = item["telefone"]
    bloqueados = armazenamento.optouts()
    cooldown = armazenamento.telefones_em_cooldown(parametros.atuais()["cooldown_dias"])
    if telefone in bloqueados or telefone in cooldown or telefone == _remetente():
        armazenamento.cancelar_alvo(item["id"])
        armazenamento.cancelar_pedido(item["id"])
        raise Bloqueado("numero bloqueado, em cooldown ou e o proprio remetente", 0)

    if not armazenamento.marcar_enviando(item["id"]):
        return None

    return {
        "alvo_id": item["id"],
        "pedido_id": pedido["id"],
        "telefone": telefone,
        "nome": item.get("nome"),
        "primeiro_nome": item.get("primeiro_nome"),
        "texto": item["texto"],
        "vencimento": item.get("vencimento"),
        "reservado_em": agora.strftime(FORMATO),
        "validade_minutos": config.CONECTOR_RESERVA_MINUTOS,
        "digitacao_segundos": humanizacao.calcular(item["texto"]),
        "esperar_segundos": 0,
        "manual": True,
    }


def devolver(alvo_id: int) -> dict:
    """Desfaz uma reserva sem gravar envio (simulacao, Ctrl+C, desistencia)."""
    item = armazenamento.alvo(alvo_id)
    if not item:
        raise Bloqueado("alvo nao encontrado", 0)
    if item["status"] != "enviando":
        return {"alvo_id": alvo_id, "status": item["status"], "devolvido": False}
    devolvido = armazenamento.devolver_alvo(alvo_id)
    return {
        "alvo_id": alvo_id,
        "status": "pendente" if devolvido else item["status"],
        "devolvido": devolvido,
    }


def confirmar(
    alvo_id: int,
    situacao: str,
    erro: str | None = None,
    momento: datetime | None = None,
) -> dict:
    """Grava o resultado do envio e devolve quanto esperar antes do proximo."""
    agora = _agora(momento)
    item = armazenamento.alvo(alvo_id)
    if not item:
        raise Bloqueado("alvo nao encontrado", 0)
    if situacao not in SITUACOES:
        raise Bloqueado(f"situacao invalida: {situacao}", 0)

    envio_id = armazenamento.registrar_envio(
        item["telefone"],
        item["texto"],
        situacao,
        alvo_id=alvo_id,
        erro=(erro or None),
    )
    # Fecha o pedido manual deste alvo, se houver um em aberto.
    armazenamento.atender_pedido_do_alvo(alvo_id, situacao)

    valores = parametros.atuais()
    pausa_automatica = False
    if situacao in config.SITUACOES_ENVIADO:
        armazenamento.zerar_falhas_consecutivas()
    elif _erro_sem_whatsapp(erro):
        # Numero inexistente nao e falha de instabilidade: registra, mas nao
        # entra na sequencia que desliga a campanha.
        armazenamento.registrar_ultimo_erro(erro or "numero sem WhatsApp")
    else:
        total_falhas = armazenamento.registrar_falha_consecutiva(
            erro or "falha no envio sem detalhe"
        )
        limite = valores["max_falhas_seguidas"]
        if limite > 0 and total_falhas >= limite:
            armazenamento.pausar(
                f"pausa automatica: {total_falhas} falhas seguidas de envio - "
                f"{erro or 'sem detalhe'}"
            )
            pausa_automatica = True

    reaberto = False
    if situacao == "falha" and not pausa_automatica:
        # max_tentativas = 1 (padrao) deixa a falha definitiva, como antes.
        tentativas = int(item.get("tentativas") or 0) + 1
        if tentativas < valores["max_tentativas"]:
            reaberto = armazenamento.reabrir_alvo(alvo_id)

    pausa = False
    if situacao in config.SITUACOES_ENVIADO:
        enviados_hoje = armazenamento.envios_do_dia(agora.strftime("%Y-%m-%d"))
        pausa = humanizacao.deve_pausar_longa(enviados_hoje)
        esperar = humanizacao.pausa_longa() if pausa else humanizacao.intervalo_entre_envios()
    else:
        esperar = float(valores["intervalo_min"])

    armazenamento.definir_proximo_envio(
        (agora + timedelta(seconds=esperar)).strftime(FORMATO)
    )

    return {
        "envio_id": envio_id,
        "alvo_id": alvo_id,
        "situacao": situacao,
        "reaberto": reaberto,
        "pausa_automatica": pausa_automatica,
        "esperar_segundos": int(esperar),
        "pausa_longa": pausa,
        "estado": estado(agora),
    }
