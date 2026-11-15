from __future__ import annotations

import json
import re
import sqlite3
import threading
from pathlib import Path
from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from .main import app
from .database import get_db
from .config import BASE_DIR
from .models import Conversa, MensagemAtendimento
from .security import verificar_api_key
from .atendimento import config, motor

# Este entrypoint e exclusivamente roteirizado, inclusive nas rotas do painel.
config.IA_BASE_URL = ''
config.IA_API_KEY = ''
config.IA_FALLBACK_BASE_URL = ''
config.IA_FALLBACK_API_KEY = ''
LOCK = threading.Lock()
STATE = Path(BASE_DIR) / 'dados' / 'whatsapp-web.sqlite3'
MAP = Path(BASE_DIR) / 'whatsapp-web' / 'compatibilidade.json'

def ledger():
    STATE.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(STATE)
    c.execute('CREATE TABLE IF NOT EXISTS messages (id TEXT PRIMARY KEY)')
    c.execute('CREATE TABLE IF NOT EXISTS contacts (jid TEXT PRIMARY KEY, conversation INTEGER)')
    c.commit()
    return c

def norm(text):
    return ' '.join(re.sub(r'[^a-z0-9]+', ' ', text.lower()).split())

class Incoming(BaseModel):
    id: str = Field(min_length=1, max_length=250)
    contato: str = Field(min_length=2, max_length=80)
    texto: str = Field(min_length=1, max_length=4000)

def record(db, conv, text):
    return motor._msg(db, conv, 'ia', text)

@app.post('/whatsapp-web/mensagem', dependencies=[Depends(verificar_api_key)])
def incoming(payload: Incoming, db: Session = Depends(get_db)):
    with LOCK:
        if config.ia_ativa():
            raise HTTPException(503, 'IA deve estar desativada')
        c = ledger()
        try:
            if c.execute('SELECT 1 FROM messages WHERE id=?', (payload.id,)).fetchone():
                return {'respostas': [], 'duplicada': True}
            # Marca antes de processar: falhas nao geram reenvio automatico.
            c.execute('INSERT INTO messages VALUES (?)', (payload.id,))
            c.commit()
            row = c.execute('SELECT conversation FROM contacts WHERE jid=?', (payload.contato,)).fetchone()
            conv = db.get(Conversa, row[0]) if row else None
            if conv is None or conv.estado == motor.ESTADO_ENCERRADA:
                conv = motor.criar_conversa(db, contato=payload.contato, canal='whatsapp_web')
                c.execute('INSERT OR REPLACE INTO contacts VALUES (?,?)', (payload.contato, conv.id))
                c.commit()
            before = db.scalar(select(MensagemAtendimento.id).where(MensagemAtendimento.conversa_id == conv.id).order_by(MensagemAtendimento.id.desc()).limit(1)) or 0
            dados = conv.dados or {}
            if dados.get('ww_modelo') and conv.estado == motor.ESTADO_IA and not motor.pedido_humano(motor.normalizar(payload.texto)):
                motor._msg(db, conv, 'cliente', payload.texto)
                try:
                    mapping = json.loads(MAP.read_text(encoding='utf-8')).get('modelos', {})
                except (OSError, ValueError):
                    mapping = {}
                apps = next((v for k, v in mapping.items() if norm(k) == norm(payload.texto)), None)
                conv.dados = {**dados, 'ww_modelo': False, 'modelo_informado': payload.texto}
                if isinstance(apps, list) and apps and all(isinstance(a, str) and a.strip() for a in apps):
                    record(db, conv, 'Aplicativos cadastrados para este aparelho: ' + ', '.join(apps) + '. A disponibilidade na loja deve ser conferida no aparelho.')
                motor.transferir(db, conv, 'Conferir aplicativo e ativacao', aviso='Vou encaminhar para um atendente conferir os aplicativos e continuar seu atendimento.')
                db.commit()
            else:
                motor.processar_mensagem_cliente(db, conv, texto=payload.texto)
            new = list(db.scalars(select(MensagemAtendimento).where(MensagemAtendimento.conversa_id == conv.id, MensagemAtendimento.id > before).order_by(MensagemAtendimento.id)))
            # Nao expor solicitacoes de midia existentes no fluxo legado/base.
            blocked = any(m.autor == 'ia' and re.search(r'foto|print|imagem|video|vídeo|audio|áudio', m.texto or '', re.I) for m in new)
            if blocked:
                for m in new:
                    if m.autor == 'ia':
                        db.delete(m)
                if conv.estado == motor.ESTADO_IA:
                    conv.dados = {**(conv.dados or {}), 'ww_modelo': True}
                    record(db, conv, 'Informe por texto a marca e o modelo exatos da TV ou do TV Box, por exemplo como aparecem nas configuracoes do aparelho. Vou consultar os aplicativos cadastrados.')
                else:
                    record(db, conv, 'Um atendente precisa conferir este caso. Aguarde o atendimento humano.')
                db.commit()
                new = list(db.scalars(select(MensagemAtendimento).where(MensagemAtendimento.conversa_id == conv.id, MensagemAtendimento.id > before).order_by(MensagemAtendimento.id)))
            return {'respostas': [m.texto.replace('[[TRANSFERIR]]', '').strip() for m in new if m.autor == 'ia' and m.tipo == 'texto' and m.texto], 'conversa_id': conv.id, 'estado': conv.estado}
        finally:
            c.close()
