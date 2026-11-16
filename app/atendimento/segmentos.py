from __future__ import annotations
import json
import re
import sqlite3
from functools import wraps
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from ..config import DATA_DIR
from ..security import verificar_api_key
from .texto import normalizar, tem

AVISO = "Aguarde um momento, nossa equipe está verificando sua solicitação"
FALHAS = ("nao funciona", "nao esta funcionando", "nao ta funcionando", "nao funcionando", "parou", "nao conecta", "nao consigo conectar", "sem internet", "sem conexao", "conectando", "caiu", "caindo", "travando", "lenta", "lento")
PADRAO = {
    "segmentos": [
        {"id": "internet", "nome": "Internet no celular Android + VPN", "termos": ["internet", "vpn", "chip", "dados moveis", "celular"], "ativo": True},
        {"id": "iptv", "nome": "IPTV / TV / canais", "termos": ["iptv", "tv", "canais", "canal", "filmes", "series"], "ativo": True}],
    "regras": [
        {"id": "falha_conexao", "segmento": "*", "intencao": "suporte", "incluir": list(FALHAS), "excluir": [], "prioridade": 100, "acao": "transferir", "pergunta": "", "ativo": True},
        {"id": "contratacao", "segmento": "*", "intencao": "contratacao", "incluir": ["quero contratar", "quero assinar", "quero comprar"], "excluir": list(FALHAS), "prioridade": 10, "acao": "continuar", "pergunta": "", "ativo": True}],
    "variaveis": [
        {"id": "operadora", "tipo": "texto", "descricao": "Operadora informada pelo cliente"},
        {"id": "trocou_servidor", "tipo": "sim_nao", "descricao": "Tentativa relatada pelo cliente"},
        {"id": "tentou_modo_aviao", "tipo": "sim_nao", "descricao": "Tentativa relatada pelo cliente"}]
}

class Entrada(BaseModel):
    versao: int = Field(ge=0)
    config: dict

class Teste(BaseModel):
    texto: str = Field(min_length=1, max_length=4000)
    servico: str = Field(default="", max_length=40)
    dados: dict = Field(default_factory=dict)
    config: dict | None = None

def validar(config):
    if not isinstance(config, dict) or set(config) != {"segmentos", "regras", "variaveis"}:
        raise ValueError("Informe segmentos, regras e variaveis.")
    for group in config.values():
        if not isinstance(group, list) or len(group) > 100:
            raise ValueError("Cada grupo aceita ate 100 itens.")
        ids = []
        for item in group:
            if not isinstance(item, dict) or not re.fullmatch(r"[a-z][a-z0-9_]{0,39}", str(item.get("id", ""))):
                raise ValueError("Identificadores: letras minusculas, numeros e sublinhado.")
            ids.append(item["id"])
        if len(ids) != len(set(ids)):
            raise ValueError("Ha identificadores duplicados no mesmo grupo.")
    def termos(values):
        if not isinstance(values, list) or len(values) > 100 or any(not isinstance(x, str) or not x.strip() or len(x) > 120 for x in values):
            raise ValueError("Termos devem ser listas de frases com ate 120 caracteres.")
    for item in config["segmentos"]:
        if not isinstance(item.get("nome"), str) or not 1 <= len(item["nome"]) <= 120 or type(item.get("ativo")) is not bool:
            raise ValueError("Segmento exige nome e ativo.")
        termos(item.get("termos"))
    services = {x["id"] for x in config["segmentos"]}
    for item in config["regras"]:
        if item.get("segmento") not in services | {"*"} or item.get("intencao") not in {"suporte", "contratacao", "informacao", "instalacao", "pagamento"}:
            raise ValueError("Servico ou intencao invalida.")
        if item.get("acao") not in {"transferir", "perguntar", "continuar"} or type(item.get("ativo")) is not bool:
            raise ValueError("Acao ou ativo invalido.")
        if type(item.get("prioridade")) is not int or not 0 <= item["prioridade"] <= 1000:
            raise ValueError("Prioridade deve ser um inteiro entre 0 e 1000.")
        termos(item.get("incluir")); termos(item.get("excluir"))
        if not item["incluir"]:
            raise ValueError("Regra exige ao menos um exemplo de entrada.")
        question = item.get("pergunta", "")
        if not isinstance(question, str) or len(question) > 600:
            raise ValueError("Pergunta deve ter ate 600 caracteres.")
        if item["acao"] == "perguntar":
            # Perguntas livres podem introduzir pedidos de midia ou falsas verificacoes.
            if question not in {"Qual mensagem de erro aparece? Descreva por texto.", "Qual e a operadora do chip?", "O problema acontece desde quando?"}:
                raise ValueError("Selecione uma das perguntas de suporte permitidas.")
        if item["acao"] == "continuar" and item["intencao"] != "contratacao":
            raise ValueError("Continuar fluxo antigo e permitido somente em contratacao.")
    for item in config["variaveis"]:
        if item.get("tipo") not in {"texto", "sim_nao"} or not isinstance(item.get("descricao"), str) or len(item["descricao"]) > 300:
            raise ValueError("Variavel exige tipo texto/sim_nao e descricao de ate 300 caracteres.")
    if len(json.dumps(config)) > 150000:
        raise ValueError("Configuracao muito grande.")
    return config

def banco():
    db = sqlite3.connect(DATA_DIR / "segmentos.db", timeout=10)
    db.execute("CREATE TABLE IF NOT EXISTS versoes (id INTEGER PRIMARY KEY, config TEXT NOT NULL, criada_em TEXT DEFAULT CURRENT_TIMESTAMP)")
    with db:
        db.execute("INSERT OR IGNORE INTO versoes(id,config) VALUES(0,?)", (json.dumps(PADRAO, ensure_ascii=False),))
    return db

def carregar():
    db = banco()
    try:
        row = db.execute("SELECT id,config FROM versoes ORDER BY id DESC LIMIT 1").fetchone()
        return {"versao": row[0], "config": validar(json.loads(row[1]))}
    finally:
        db.close()

def publicar(payload):
    config = validar(payload.config)
    db = banco()
    try:
        db.execute("BEGIN IMMEDIATE")
        version = db.execute("SELECT MAX(id) FROM versoes").fetchone()[0]
        if version != payload.versao:
            raise HTTPException(409, "Outra publicacao ocorreu. Reabra a tela antes de editar.")
        db.execute("INSERT INTO versoes(id,config) VALUES(?,?)", (version + 1, json.dumps(config, ensure_ascii=False)))
        db.commit()
        return {"versao": version + 1, "config": config}
    finally:
        db.close()

def classificar(texto, servico="", dados=None, config=None):
    cfg = validar(config) if config is not None else carregar()["config"]
    text = normalizar(texto)
    services = [s for s in cfg["segmentos"] if s["ativo"] and tem(text, *s["termos"])]
    explicit = services[0]["id"] if len(services) == 1 else ""
    service = explicit or (servico if not services else "")
    failure = tem(text, *FALHAS)
    candidates = [r for r in cfg["regras"] if r["ativo"] and r["segmento"] in {"*", service} and tem(text, *r["incluir"]) and not tem(text, *r["excluir"])]
    candidates.sort(key=lambda r: (r["intencao"] == "suporte", r["prioridade"]), reverse=True)
    rule = candidates[0] if candidates else None
    support = failure or bool(rule and rule["intencao"] == "suporte") or (dados or {}).get("intencao") == "suporte"
    if support:
        if not service:
            return {"servico": "", "intencao": "suporte", "regra": "esclarecer_servico", "acao": "perguntar", "pergunta": "O problema e na internet do celular (VPN) ou no IPTV/TV?"}
        if not rule or rule["intencao"] != "suporte":
            rule = {"id": "suporte_contextual", "acao": "transferir", "pergunta": ""}
        return {"servico": service, "intencao": "suporte", "regra": rule["id"], "acao": rule["acao"], "pergunta": rule.get("pergunta", "")}
    return {"servico": service, "intencao": rule["intencao"] if rule else "indefinida", "regra": rule["id"] if rule else None, "acao": rule["acao"] if rule else "continuar", "pergunta": rule.get("pergunta", "") if rule else ""}

def integrar(original):
    @wraps(original)
    def tratar(db, conversa, texto):
        from . import motor
        if conversa.estado != motor.ESTADO_IA:
            return []
        data = dict(conversa.dados or {})
        if normalizar(texto) in {"menu", "inicio", "voltar", "reiniciar", "comecar de novo"}:
            data.pop("intencao", None)
            conversa.dados = data
            return original(db, conversa, texto)
        result = classificar(texto, data.get("servico", ""), data)
        if result["intencao"] == "indefinida":
            if data.get("servico") == "internet" and tem(normalizar(texto), "samsung", "lg", "tcl", "xiaomi", "motorola") and not tem(normalizar(texto), "tv", "iptv", "televisao"):
                return [motor._msg(db, conversa, "ia", "Estamos falando da internet do celular. Qual e a sua duvida ou dificuldade?")]
            return original(db, conversa, texto)
        if result["servico"]:
            data["servico"] = result["servico"]
        data.update(intencao=result["intencao"], regra_segmento=result["regra"])
        if result["intencao"] == "suporte":
            data["quer_contratar"] = False
        conversa.dados = data
        if result["acao"] == "transferir":
            return motor.transferir(db, conversa, "Suporte/triagem: " + (result["servico"] or "servico a confirmar"), aviso=AVISO)
        if result["acao"] == "perguntar":
            if data.get("pergunta_segmento") == result["regra"]:
                return motor.transferir(db, conversa, "Triagem necessita verificacao", aviso=AVISO)
            conversa.dados = {**data, "pergunta_segmento": result["regra"]}
            return [motor._msg(db, conversa, "ia", result["pergunta"])]
        return original(db, conversa, texto)
    return tratar

router = APIRouter(prefix="/atendimento/segmentos", dependencies=[Depends(verificar_api_key)])
@router.get("")
def listar():
    return carregar()
@router.post("/publicar")
def salvar(payload: Entrada):
    try:
        return publicar(payload)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
@router.post("/testar")
def testar(payload: Teste):
    try:
        return classificar(payload.texto, payload.servico, payload.dados, payload.config)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
@router.get("/historico")
def historico():
    db = banco()
    try:
        return {"itens": [{"versao": r[0], "criada_em": r[1], "config": json.loads(r[2])} for r in db.execute("SELECT id,criada_em,config FROM versoes ORDER BY id DESC LIMIT 30")]}
    finally:
        db.close()
