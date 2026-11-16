$projeto = "D:\planilhas\ia atendimento"

$alvo = Get-ChildItem -Path $projeto -Recurse -Filter "motor.py" -File | Select-Object -First 1

if (-not $alvo) {
    Write-Host "Nao encontrei motor.py dentro de: $projeto"
    exit
}

$pasta = $alvo.DirectoryName
Write-Host "motor.py encontrado em:"
Write-Host $alvo.FullName

$copia = Join-Path $pasta "motor.py.antes-teste-ssh.bak"
Copy-Item $alvo.FullName $copia -Force
Write-Host "Backup criado em:"
Write-Host $copia

$arquivoTeste = Join-Path $pasta "testes_ssh.py"

$codigoTeste = @'
from __future__ import annotations

import json
import os
import random
import sqlite3
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

from .config import DATADIR

URL_CRIAR_TESTE = "https://painel.linksshbrasil.com.br/api/usuario/criar_teste.php"
INTERVALO_HORAS = 48
MINUTOS_TESTE = 180

ARQUIVO = Path(DATADIR) / "testes_ssh.db"


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


def criar_teste(contato: str) -> dict:
    token = os.environ.get("LINKSSH_TOKEN", "")

    if not token:
        return {"ok": False, "erro": "Token LINKSSH_TOKEN nao configurado"}

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
'@

if (-not (Test-Path $arquivoTeste)) {
    Set-Content -Path $arquivoTeste -Value $codigoTeste -Encoding UTF8
    Write-Host "Arquivo criado:"
    Write-Host $arquivoTeste
} else {
    Write-Host "testes_ssh.py ja existe. Nao foi alterado."
}

$conteudo = Get-Content $alvo.FullName -Raw

if ($conteudo -notmatch "from \.testes_ssh import") {
    $conteudo = $conteudo -replace "(from \. import aplicativos[^\r\n]*\r?\n)", "`$1from .testes_ssh import criar_teste, pode_criar`r`n"
}

$novoBloco = @'
        if not pode_criar(conversa.contato):
            return transferir(
                db,
                conversa,
                "Cliente solicitou outro teste antes do intervalo de 48 horas",
                aviso=(
                    "Para solicitar um novo teste, vou encaminhar você "
                    "para o atendimento humano."
                ),
            )

        resultado = criar_teste(conversa.contato)

        if not resultado.get("ok"):
            return transferir(
                db,
                conversa,
                "Falha ao criar teste SSH",
                aviso=(
                    "Não consegui criar seu teste agora. "
                    "Vou encaminhar você para o atendimento humano."
                ),
            )

        _atualizar_dados(
            conversa,
            teste=True,
            teste_ssh_login=resultado["login"],
            teste_ssh_expira=resultado["expira"],
        )

        return [
            _msg(
                db,
                conversa,
                "ia",
                (
                    "Seu teste SSH de 3 horas foi criado.\n\n"
                    f"Login: {resultado['login']}\n"
                    f"Senha: {resultado['senha']}\n"
                    f"Validade: {resultado['expira']}\n\n"
                    "Use esses dados no aplicativo para conectar."
                ),
            )
        ]
'@

$padrao = '(?m)^[ \t]*return iniciar_internet\(db, conversa, texto, teste=True, contratar=True\)[ \t]*\r?\n'

if ($conteudo -match $padrao) {
    $conteudo = [regex]::Replace($conteudo, $padrao, $novoBloco)
    Set-Content -Path $alvo.FullName -Value $conteudo -Encoding UTF8
    Write-Host "Integracao inserida no motor.py com sucesso."
} else {
    Write-Host "Nao encontrei a linha esperada no motor.py."
    Write-Host "Nenhuma alteracao foi aplicada."
}