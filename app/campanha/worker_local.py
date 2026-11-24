"""Liga e desliga o worker do WhatsApp pelo painel.

O painel nao envia nada por aqui: estes comandos apenas sobem o processo Node
que ja existe (`campanha-whatsapp/worker.cjs`) em segundo plano, com o mesmo
perfil exclusivo do Chrome. Subir em modo `manual` nao envia mensagem sozinho:
o worker so age quando o painel pede um alvo pelo botao "Enviar agora".

Encerrar: o painel marca um pedido e o worker fecha sozinho no proximo pulso
(fecha o Chrome do jeito certo, sem deixar `lockfile`). Se ele nao responder,
`desligar(forcar=True)` mata o processo e os filhos (o Chrome dele).
"""

from __future__ import annotations

import ctypes
import os
import shutil
import signal
import subprocess
import time
from pathlib import Path

from . import armazenamento, config

PASTA = config.BASE_DIR / "campanha-whatsapp"
SCRIPT = PASTA / "worker.cjs"
SAIDA = config.BASE_DIR / "dados" / "campanha-worker-saida.log"

MODOS = {
    "manual": ["--manual"],
    "enviar": ["--enviar"],
    "parear": ["--parear", "--mostrar"],
}


class WorkerIndisponivel(RuntimeError):
    """Node ausente, worker.cjs ausente ou modo invalido."""


def _versao(chave: str) -> tuple[int, ...]:
    partes: list[int] = []
    for parte in chave.lstrip("vV").split("."):
        try:
            partes.append(int(parte))
        except ValueError:
            partes.append(0)
    return tuple(partes)


def achar_node() -> str:
    explicito = os.getenv("CAMPANHA_NODE", "").strip()
    if explicito and Path(explicito).is_file():
        return explicito
    achado = shutil.which("node")
    if achado:
        return achado
    raiz = Path(os.environ.get("APPDATA", "")) / "fnm" / "node-versions"
    if raiz.is_dir():
        pastas = sorted(
            (p for p in raiz.iterdir() if p.is_dir() and p.name[:1].lower() == "v"),
            key=lambda p: _versao(p.name),
            reverse=True,
        )
        for pasta in pastas:
            for nome in ("node.exe", "node"):
                candidato = pasta / "installation" / nome
                if candidato.is_file():
                    return str(candidato)
    raise WorkerIndisponivel(
        "Node.js nao encontrado. Instale com: winget install OpenJS.NodeJS.LTS"
    )


def _pid_vivo(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        kernel32 = ctypes.windll.kernel32
        alca = kernel32.OpenProcess(0x1000, False, int(pid))
        if not alca:
            return False
        kernel32.CloseHandle(alca)
        return True
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def status(segundos: int = 45) -> dict:
    dados = armazenamento.worker_status(segundos)
    pid = armazenamento.worker_pid()
    try:
        node = achar_node()
    except WorkerIndisponivel:
        node = ""
    return {
        **dados,
        "pid": pid,
        "pid_vivo": _pid_vivo(pid),
        "node": node,
        "script": str(SCRIPT),
        "numero_conectado": armazenamento.numero_conectado(),
    }


def ligar(modo: str = "manual") -> dict:
    if modo not in MODOS:
        raise WorkerIndisponivel("modo invalido: use 'manual', 'enviar' ou 'parear'")
    if not SCRIPT.is_file():
        raise WorkerIndisponivel(f"worker nao encontrado em {SCRIPT}")

    pid_salvo = armazenamento.worker_pid()
    if pid_salvo and not _pid_vivo(pid_salvo):
        armazenamento.limpar_worker()

    atual = status()
    if atual["online"] and not atual["pid_vivo"]:
        armazenamento.limpar_worker()
        atual = status()

    if atual["online"]:
        return {
            "ligado": False,
            "motivo": f"o robo ja esta online (modo {atual['modo']})",
            "worker": atual,
        }
    if atual["pid_vivo"]:
        return {
            "ligado": False,
            "motivo": "o robo esta iniciando agora; aguarde a conexao",
            "worker": atual,
        }

    node = achar_node()
    SAIDA.parent.mkdir(parents=True, exist_ok=True)

    opcoes = 0
    if os.name == "nt":
        opcoes = (
            subprocess.DETACHED_PROCESS
            | subprocess.CREATE_NEW_PROCESS_GROUP
            | subprocess.CREATE_NO_WINDOW
        )

    with open(SAIDA, "a", encoding="utf-8", errors="replace") as saida:
        processo = subprocess.Popen(
            [node, str(SCRIPT), *MODOS[modo]],
            cwd=str(config.BASE_DIR),
            stdin=subprocess.DEVNULL,
            stdout=saida,
            stderr=subprocess.STDOUT,
            creationflags=opcoes,
            close_fds=True,
        )

    armazenamento.salvar_worker_pid(processo.pid)
    armazenamento.limpar_pedido_parada()
    return {
        "ligado": True,
        "pid": processo.pid,
        "modo": modo,
        "worker": status(),
    }


def _pids_do_worker() -> list[int]:
    if os.name != "nt":
        return []
    script = (
        "Get-CimInstance Win32_Process -Filter \"Name='node.exe'\" | "
        "Where-Object { $_.CommandLine -match 'worker\\.cjs' } | "
        "ForEach-Object { $_.ProcessId }"
    )
    try:
        resultado = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            text=True,
            timeout=25,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    return [
        int(linha.strip())
        for linha in (resultado.stdout or "").splitlines()
        if linha.strip().isdigit()
    ]


def _matar(pid: int) -> None:
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return
    os.kill(pid, signal.SIGTERM)


def desligar(forcar: bool = False) -> dict:
    """Pede o encerramento; se o worker nao sair, encerra de verdade."""
    pid = armazenamento.worker_pid()

    if forcar:
        if not pid or not _pid_vivo(pid):
            armazenamento.limpar_worker()
            return {"desligado": False, "motivo": "nenhum robo em execucao"}
        _matar(pid)
        armazenamento.limpar_worker()
        armazenamento.limpar_pedido_parada()
        return {"desligado": True, "pid": pid, "motivo": "encerrado a forca"}

    momento = armazenamento.pedir_parada_worker()

    for _ in range(12):
        time.sleep(1)
        if not pid or not _pid_vivo(pid):
            armazenamento.limpar_worker()
            armazenamento.limpar_pedido_parada()
            return {
                "desligado": True,
                "pid": pid,
                "motivo": "encerrado pelo pedido do painel",
            }

    alvos: list[int] = []
    if pid and _pid_vivo(pid):
        alvos.append(pid)
    for extra in _pids_do_worker():
        if extra not in alvos and _pid_vivo(extra):
            alvos.append(extra)

    for alvo in alvos:
        _matar(alvo)

    time.sleep(2)
    armazenamento.limpar_worker()
    armazenamento.limpar_pedido_parada()
    return {
        "desligado": True,
        "pid": pid,
        "motivo": "encerrado a forca apos nao responder ao pedido",
        "processos_encerrados": alvos,
    }


def desconectar(limite: int = 150) -> dict:
    if not SCRIPT.is_file():
        raise WorkerIndisponivel(f"worker nao encontrado em {SCRIPT}")
    node = achar_node()

    atual = status()
    if atual["pid"] and (atual["online"] or atual["pid_vivo"]):
        desligar()
        for _ in range(30):
            time.sleep(1)
            if not _pid_vivo(atual["pid"]):
                break
        else:
            desligar(forcar=True)
            time.sleep(2)

    restantes = [p for p in _pids_do_worker() if _pid_vivo(p)]
    for extra in restantes:
        _matar(extra)
    if restantes:
        time.sleep(3)

    try:
        resultado = subprocess.run(
            [node, str(SCRIPT), "--desconectar"],
            cwd=str(config.BASE_DIR),
            capture_output=True,
            text=True,
            timeout=limite,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
    except subprocess.TimeoutExpired as erro:
        raise WorkerIndisponivel(
            "o WhatsApp nao respondeu a tempo; tente de novo em instantes"
        ) from erro

    saida = "\n".join(
        linha.strip() for linha in (resultado.stdout or "").splitlines() if linha.strip()
    )
    if resultado.returncode != 0:
        raise WorkerIndisponivel(saida[-400:] or "nao foi possivel desconectar")

    armazenamento.salvar_numero_conectado("")
    return {"desconectado": True, "saida": saida[-600:]}
