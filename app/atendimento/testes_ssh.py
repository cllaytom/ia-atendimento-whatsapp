from __future__ import annotations

import json
import random
import sqlite3
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path


URL_CRIAR_TESTE = "https://painel.linksshbrasil.com.br/api/usuario/criar_teste.php"
INTERVALO_HORAS = 48
MINUTOS_TESTE = 180

ARQUIVO = Path(__file__).resolve().parent / "testes_ssh.db"


def _banco() -> sqlite3.Connection:
    ARQUIVO.parent.mkdir(parents=True, exist_ok=True)

    db = sqlite3.connect(ARQUIVO, timeout=10)
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS testes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            contato TEXT NOT NULL,
            login TEXT NOT NULL,
            senha TEXT NOT NULL,
            criado_em TEXT NOT NULL,
            expira_em TEXT,
            status TEXT NOT NULL
        )
        """
    )
    db.commit()
    return db


def pode_criar(contato: str) -> bool:
    limite = (datetime.utcnow() - timedelta(hours=INTERVALO_HORAS)).isoformat()

    with _banco() as db:
        linha = db.execute(
            """
            SELECT COUNT(*)
            FROM testes
            WHERE contato = ?
              AND status = 'criado'
              AND criado_em >= ?
            """,
            (contato, limite),
        ).fetchone()

    return linha[0] == 0


def criar_teste(contato: str, token: str) -> dict:
    login = "teste" + str(random.randint(1000, 9999))
    senha = "".join(str(random.randint(0, 9)) for _ in range(8))

    corpo = json.dumps(
        {
            "login": login,
            "senha": senha,
            "minutos": MINUTOS_TESTE,
            "nome": "Teste tecnico SSH 3h",
            "tipo": "ssh",
            "valor": "0.00",
        }
    ).encode("utf-8")

    requisicao = urllib.request.Request(
        URL_CRIAR_TESTE,
        data=corpo,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8",
        },
    )

    try:
        with urllib.request.urlopen(requisicao, timeout=30) as resposta:
            dados = json.loads(resposta.read().decode("utf-8"))
    except Exception as erro:
        return {"ok": False, "erro": str(erro)}

    if not dados.get("success"):
        return {"ok": False, "erro": "A API nao confirmou a criacao"}

    expira = (dados.get("data") or {}).get("expira") or ""
    agora = datetime.utcnow().isoformat()

    with _banco() as db:
        db.execute(
            """
            INSERT INTO testes
            (contato, login, senha, criado_em, expira_em, status)
            VALUES (?, ?, ?, ?, ?, 'criado')
            """,
            (contato, login, senha, agora, expira),
        )
        db.commit()

    return {
        "ok": True,
        "login": login,
        "senha": senha,
        "expira": expira,
    }

