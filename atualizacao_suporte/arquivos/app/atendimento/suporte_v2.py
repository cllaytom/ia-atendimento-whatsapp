"""Adaptadores de suporte, revisao e metricas. Nao envia WhatsApp."""
import contextvars
import json
import logging
import re
import sqlite3
import time
from functools import wraps
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from ..config import DATA_DIR
from ..database import get_db
from ..models import Duvida
from ..security import verificar_api_key
from . import config, conhecimento, motor, ia, oferta, segmentos
from .suporte_regras import AVISO, ENSINOS, PENDENCIAS, avancar, normalizar, possui

log = logging.getLogger("atendimento.tempos")
tempo_ia = contextvars.ContextVar("tempo_ia", default=0.0)
router = APIRouter(prefix="/atendimento/revisao", dependencies=[Depends(verificar_api_key)])

def banco():
    db = sqlite3.connect(DATA_DIR / "revisao_suporte.db", timeout=10)
    db.execute("CREATE TABLE IF NOT EXISTS pendencias (id INTEGER PRIMARY KEY, pergunta TEXT UNIQUE, contexto TEXT, status TEXT DEFAULT 'pendente', resposta TEXT DEFAULT '')")
    with db:
        db.executemany("INSERT OR IGNORE INTO pendencias(pergunta,contexto) VALUES(?,?)", PENDENCIAS)
    return db

def limpar(texto):
    current = config.LINK_APP_ANDROID
    texto = re.sub(r"https?://[^\s<>]+", lambda m: current if current and current.startswith("https://") else "[link atual não configurado]", texto)
    if re.search(r"(?:mand|envi|pec|precis).{0,55}(?:print|foto|imagem|video|audio)", normalizar(texto)):
        return "Descreva por texto a mensagem de erro e o aparelho usado. Não envie senhas ou dados de pagamento."
    return texto

def tags(texto):
    t = normalizar(texto)
    net = possui(t,("internet", "vpn", "chip", "celular", "operadora", "recarga", "modo aviao"))
    tv = possui(t,("iptv", "tv", "tv box", "canais"))
    service = "internet" if net and not tv else "iptv" if tv and not net else "geral"
    intent = "suporte" if possui(t,("conecta", "conexao", "erro", "falha", "nao funciona", "modo aviao", "configuracoes", "sinal", "reiniciar", "tentativas", "suporte")) else "pagamento" if possui(t,("paguei", "renovacao", "renovar", "pagamento")) else "informacao"
    return service, intent

@router.get("")
def listar(tipo: str = "base", servico: str = "", intencao: str = "", status: str = "", q: str = "", db=Depends(get_db)):
    if tipo not in {"base", "duvidas"}: raise HTTPException(422,"Tipo invalido")
    if tipo == "base":
        items = [{**x,"id":i,"origem":"base","status":"ativo"} for i,x in enumerate(conhecimento.carregar())]
    else:
        items = [{"id":x.id,"pergunta":x.pergunta,"resposta":x.resposta or "","status":x.status,"origem":"duvida","contexto":x.contexto or ""} for x in db.scalars(select(Duvida).order_by(Duvida.id.desc())).all()]
        local = banco()
        try:
            items += [dict(zip(("id","pergunta","contexto","status","resposta"), row), origem="revisao",servico="internet",intencao="suporte") for row in local.execute("SELECT id,pergunta,contexto,status,resposta FROM pendencias")]
        finally: local.close()
    result=[]
    for item in items:
        s,i = tags(item["pergunta"])
        item.setdefault("servico",s); item.setdefault("intencao",i)
        text = normalizar(item["pergunta"] + " " + item.get("resposta", ""))
        if servico and item["servico"] != servico: continue
        if intencao and item["intencao"] != intencao: continue
        if status and item["status"] != status: continue
        if q and normalizar(q) not in text: continue
        result.append(item)
    return {"itens":result,"total":len(result),"classificacao":"automatica_por_termos; revise assuntos ambiguos"}

class Revisao(BaseModel):
    resposta: str = Field(min_length=1,max_length=4000)

@router.post("/{item_id}/responder")
def responder(item_id: int, payload: Revisao):
    # Somente pendencias curadas; duvidas de clientes usam a rota existente.
    answer=payload.resposta.strip()
    if not answer or limpar(answer)!=answer or re.search(r"(?:\d[ ().+-]*){11,}|\b(?:senha|token)\s*[:=]\s*\S+", normalizar(answer)):
        raise HTTPException(422,"Revise: texto vazio, midia, link ou dado particular nao permitido.")
    db=banco()
    try:
        db.execute("BEGIN IMMEDIATE")
        row=db.execute("SELECT pergunta,status FROM pendencias WHERE id=?",(item_id,)).fetchone()
        if not row: raise HTTPException(404,"Pendencia nao encontrada")
        if row[1]!="pendente": raise HTTPException(409,"Pendencia ja respondida")
        conhecimento.adicionar(row[0],answer,[normalizar(row[0])])
        db.execute("UPDATE pendencias SET status='respondida',resposta=? WHERE id=?",(answer,item_id));db.commit()
        return {"salvo":True,"enviado_ao_cliente":False}
    finally: db.close()

def inicializar():
    if getattr(motor,"_suporte_v2",False): return
    arquivo=config.ARQUIVO_CONHECIMENTO
    # Backup anterior a primeira insercao; nao sobrescrever backup existente.
    backup=arquivo.with_name(arquivo.name+".antes-suporte-v2.bak")
    if arquivo.exists() and not backup.exists():
        with backup.open("xb") as f: f.write(arquivo.read_bytes())
    existing={normalizar(x["pergunta"]) for x in conhecimento.carregar()}
    for question,answer in ENSINOS:
        if normalizar(question) not in existing:
            conhecimento.adicionar(question,answer,[normalizar(question)])
    local=banco();local.close()
    config.PAUSA_ATIVA=True
    config.PAUSA_MIN=config.PAUSA_MAX=config.PAUSA_TETO=2.0
    config.PAUSA_POR_CARACTERE=0.0
    oferta.MSG_TRANSFERENCIA=oferta.MSG_TRANSFERENCIA_PEDIDO=AVISO
    original_load=conhecimento.carregar
    def carregar():
        return [{**x,"resposta":limpar(x["resposta"])} for x in original_load()]
    conhecimento.carregar=carregar
    original_transfer=motor.transferir
    def transferir(db,conversa,motivo,aviso=None):
        return original_transfer(db,conversa,motivo,aviso="" if aviso=="" else AVISO)
    motor.transferir=transferir
    original_msg=motor._msg
    def mensagem(db,conversa,autor,texto,*args,**kwargs):
        return original_msg(db,conversa,autor,limpar(texto) if autor=="ia" else texto,*args,**kwargs)
    motor._msg=mensagem
    original_query=ia._consultar
    def consultar(payload):
        start=time.perf_counter()
        try: return original_query(payload)
        finally: tempo_ia.set(tempo_ia.get()+time.perf_counter()-start)
    ia._consultar=consultar
    original_process=motor.processar_mensagem_cliente
    @wraps(original_process)
    def processar(*args,**kwargs):
        token=tempo_ia.set(0.0);start=time.perf_counter()
        try: return original_process(*args,**kwargs)
        finally:
            log.warning("Processamento atendimento=%.3fs; consulta IA=%.3fs (0 pode indicar fluxo roteirizado)",time.perf_counter()-start,tempo_ia.get())
            tempo_ia.reset(token)
    motor.processar_mensagem_cliente=processar
    original=motor.tratar_texto
    def tratar(db,conversa,texto):
        if conversa.estado!=motor.ESTADO_IA: return []
        t=normalizar(texto);data=dict(conversa.dados or {})
        if t in {"menu","inicio","voltar","reiniciar","comecar de novo"}:
            data.pop("suporte_v2",None);data.pop("intencao",None);data.pop("pergunta_segmento",None);conversa.dados=data
            return original(db,conversa,texto)
        if possui(t,("link do aplicativo","link do app","qual aplicativo","qual app","me manda o app","manda o aplicativo")):
            link=config.LINK_APP_ANDROID
            answer="Use somente o aplicativo atual: "+link if link and link.startswith("https://") else "O link do aplicativo atual ainda não está configurado. Não vou indicar aplicativos dos históricos antigos."
            return [motor._msg(db,conversa,"ia",answer)]
        if t in {"atendente","humano"} or possui(t,("falar com atendente","falar com humano","quero um atendente","quero falar com a equipe")):
            return motor.transferir(db,conversa,"Pedido explicito de atendimento humano")
        messages=motor._historico(db,conversa)
        history=[x["texto"] for x in messages if x.get("autor")=="cliente"]
        result=avancar(texto,data.get("suporte_v2"),data.get("servico",""),history)
        if result is None: return original(db,conversa,texto)
        if result["acao"]=="delegar_iptv":
            # Nao aplicar procedimentos de celular a TV, nem transferir so pela palavra falha.
            data.update(servico="iptv",intencao="suporte",suporte_v2=result["estado"])
            if not data.get("iptv_perguntado"):
                data["iptv_perguntado"]=True;conversa.dados=data
                return [motor._msg(db,conversa,"ia",result["resposta"])]
            conversa.dados=data
            answer=ia.responder(messages,"suporte_iptv",data)
            if answer and answer.texto and not answer.transferir:
                return [motor._msg(db,conversa,"ia",answer.texto)]
            return motor.transferir(db,conversa,"IPTV: sem orientacao aprovada suficiente apos triagem")
        data.update(suporte_v2=result["estado"],intencao="suporte",quer_contratar=False)
        if result["estado"].get("servico"): data["servico"]=result["estado"]["servico"]
        if not result["estado"].get("ativo"):
            data.pop("intencao",None);data.pop("pergunta_segmento",None);conversa.etapa=motor.MENU
        conversa.dados=data
        if result["acao"]=="transferir":
            return motor.transferir(db,conversa,"Suporte: verificacoes esgotadas, acao administrativa ou pedido humano")
        return [motor._msg(db,conversa,"ia",result["resposta"])]
    motor.tratar_texto=tratar
    motor._suporte_v2=True
