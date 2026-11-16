from __future__ import annotations
import re
import logging
import time
from sqlalchemy import select
from ..database import SessionLocal
from ..models import Conversa
from . import motor, pausas

CANAL = "whatsapp"

def normalizar_contato(bruto: str) -> str:
    # Nao inferir pais e nunca converter nomes em contatos.
    raw = (bruto or "").strip()
    if not re.fullmatch(r"[+0-9 ()-]+", raw):
        raise ValueError("Informe numero internacional, nunca nome de contato.")
    digits = re.sub(r"\D", "", raw)
    if not 12 <= len(digits) <= 15:
        raise ValueError("Numero internacional invalido.")
    return digits

def _conversa_aberta(db, contato):
    return db.scalars(select(Conversa).where(
        Conversa.contato == contato, Conversa.canal == CANAL,
        Conversa.estado != motor.ESTADO_ENCERRADA
    ).order_by(Conversa.id.desc()).limit(1)).first()

def receber(contato, texto, nome=None, imagem=None):
    contato = normalizar_contato(contato)
    if imagem:
        raise ValueError("Este canal recebe somente texto.")
    texto = (texto or "").strip()
    if not texto or len(texto) > 4000:
        raise ValueError("Texto vazio ou acima do limite.")
    db = SessionLocal()
    try:
        conv = _conversa_aberta(db, contato)
        if conv is None:
            conv = motor.criar_conversa(db, contato=contato, nome=nome, canal=CANAL)
        novas = motor.processar_mensagem_cliente(db, conv, texto=texto)
        respostas = [m.texto for m in novas if m.autor == "ia" and m.texto]
        # Protecao temporaria: nao enviar pedidos de midia do motor legado.
        if any(re.search(r"(?:mand|envi|precis).{0,55}(?:foto|print|imagem|v[ií]deo|[aá]udio)", r, re.I) for r in respostas):
            motor.transferir(db, conv, "Conferir aplicativos por marca/modelo", aviso="")
            db.commit()
            respostas = ["Aguarde um momento, nossa equipe está verificando sua solicitação"]
        # O conector envia a lista em um unico balao. Aplica a regra existente
        # uma vez para esse envio, sem alterar a configuracao da IA.
        # Nenhum bloqueio global e introduzido: a espera e desta requisicao.
        if respostas:
            # Encerra qualquer transacao de leitura antes da espera para que
            # uma intervencao humana seja visivel na consulta seguinte.
            db.commit()
            inicio_pausa = time.perf_counter()
            pausas.esperar("\n\n".join(respostas))
            logging.getLogger("atendimento.tempos").warning("Pausa adicional aplicada=%.3fs (alvo 2s)", time.perf_counter()-inicio_pausa)
        db.refresh(conv)
        # Se o humano assumiu durante a pausa, nao devolve resposta pendente.
        if conv.estado in (motor.ESTADO_HUMANO, motor.ESTADO_ENCERRADA):
            respostas = []
        return {"conversa_id": conv.id, "estado": conv.estado, "etapa": conv.etapa,
                "respostas": [r.replace("[[TRANSFERIR]]", "").strip() for r in respostas],
                "alerta_humano": conv.estado in (motor.ESTADO_AGUARDANDO, motor.ESTADO_HUMANO),
                "motivo": conv.motivo_transferencia, "resumo": conv.resumo}
    finally:
        db.close()

def status(contato):
    contato = normalizar_contato(contato)
    db = SessionLocal()
    try:
        conv = _conversa_aberta(db, contato)
        if conv is None:
            return {"contato": contato, "existe": False}
        return {"contato": contato, "existe": True, "conversa_id": conv.id,
                "estado": conv.estado, "etapa": conv.etapa,
                "dados": conv.dados or {}, "resumo": conv.resumo}
    finally:
        db.close()

def encerrar(contato):
    contato = normalizar_contato(contato)
    db = SessionLocal()
    try:
        conv = _conversa_aberta(db, contato)
        if conv is None:
            return False
        conv.estado = motor.ESTADO_ENCERRADA
        db.commit()
        return True
    finally:
        db.close()

def alerta_de_transferencia(contato, resultado):
    return ("Atendimento humano necessario\nCliente: +" + normalizar_contato(contato)
            + "\nMotivo: " + str(resultado.get("motivo") or "nao informado")
            + "\n" + str(resultado.get("resumo") or ""))
