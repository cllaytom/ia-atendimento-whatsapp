"""Banco proprio da campanha (dados/campanha.db).

Nao usa SQLAlchemy e nao toca em assinaturas.db. O arquivo so e criado
quando alguem grava algo (fila ou opt-out); leituras em base vazia
devolvem estruturas vazias.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta

from . import config

DDL = """
CREATE TABLE IF NOT EXISTS optouts (
    telefone TEXT PRIMARY KEY,
    motivo TEXT NOT NULL DEFAULT '',
    origem TEXT NOT NULL DEFAULT 'manual',
    criado_em TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS alvos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    assinatura_id INTEGER NOT NULL UNIQUE,
    telefone TEXT NOT NULL,
    nome TEXT,
    primeiro_nome TEXT,
    produto TEXT,
    vencimento TEXT,
    texto TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pendente',
    tentativas INTEGER NOT NULL DEFAULT 0,
    criado_em TEXT NOT NULL,
    atualizado_em TEXT
);
CREATE INDEX IF NOT EXISTS idx_alvos_status ON alvos(status);
CREATE TABLE IF NOT EXISTS envios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    alvo_id INTEGER,
    telefone TEXT NOT NULL,
    texto TEXT NOT NULL,
    situacao TEXT NOT NULL,
    erro TEXT,
    criado_em TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_envios_telefone ON envios(telefone, criado_em);
CREATE TABLE IF NOT EXISTS estado (
    chave TEXT PRIMARY KEY,
    valor TEXT NOT NULL,
    atualizado_em TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS pedidos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    alvo_id INTEGER NOT NULL,
    criado_em TEXT NOT NULL,
    atendido_em TEXT,
    situacao TEXT NOT NULL DEFAULT 'pendente'
);
CREATE INDEX IF NOT EXISTS idx_pedidos_situacao ON pedidos(situacao);
CREATE TABLE IF NOT EXISTS contatos_whatsapp (
    telefone TEXT PRIMARY KEY,
    nome TEXT,
    atualizado_em TEXT NOT NULL
);
"""


def _momento() -> datetime:
    """Relogio unico do banco (os testes congelam aqui)."""
    return datetime.now()


def agora() -> str:
    return _momento().strftime("%Y-%m-%d %H:%M:%S")


def existe() -> bool:
    return config.BANCO_CAMPANHA.exists()


def _conectar() -> sqlite3.Connection:
    config.BANCO_CAMPANHA.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(config.BANCO_CAMPANHA, timeout=10)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    return con


@contextmanager
def _abrir(escrita: bool = False):
    con = _conectar()
    try:
        con.executescript(DDL)
        yield con
        if escrita:
            con.commit()
    finally:
        con.close()


# ------------------------------- opt-out ----------------------------------

def optouts() -> dict[str, dict]:
    if not existe():
        return {}
    with _abrir() as con:
        linhas = con.execute("SELECT * FROM optouts ORDER BY criado_em DESC").fetchall()
    return {linha["telefone"]: dict(linha) for linha in linhas}


def bloquear(telefone: str, motivo: str = "", origem: str = "manual") -> bool:
    with _abrir(escrita=True) as con:
        cursor = con.execute(
            "INSERT INTO optouts (telefone, motivo, origem, criado_em) VALUES (?,?,?,?) "
            "ON CONFLICT(telefone) DO UPDATE SET motivo=excluded.motivo, origem=excluded.origem",
            (telefone, (motivo or "").strip()[:200], origem, agora()),
        )
        return cursor.rowcount > 0


def desbloquear(telefone: str) -> bool:
    if not existe():
        return False
    with _abrir(escrita=True) as con:
        cursor = con.execute("DELETE FROM optouts WHERE telefone = ?", (telefone,))
        return cursor.rowcount > 0


# -------------------------------- cooldown --------------------------------

def telefones_em_cooldown(dias: int | None = None) -> set[str]:
    dias = config.COOLDOWN_DIAS if dias is None else dias
    if not existe():
        return set()
    limite = (_momento() - timedelta(days=dias)).strftime("%Y-%m-%d %H:%M:%S")
    with _abrir() as con:
        linhas = con.execute(
            "SELECT DISTINCT telefone FROM envios "
            "WHERE situacao IN (?,?) AND criado_em >= ?",
            (*config.SITUACOES_ENVIADO, limite),
        ).fetchall()
    return {linha["telefone"] for linha in linhas}


# ----------------------------------- fila ---------------------------------

def telefones_na_fila() -> set[str]:
    if not existe():
        return set()
    with _abrir() as con:
        linhas = con.execute(
            "SELECT DISTINCT telefone FROM alvos WHERE status IN ('pendente','enviando')"
        ).fetchall()
    return {linha["telefone"] for linha in linhas}


def telefones_registrados() -> set[str]:
    """Todos os telefones que ja passaram pelo banco da campanha (qualquer status)."""
    if not existe():
        return set()
    with _abrir() as con:
        linhas = con.execute("SELECT DISTINCT telefone FROM alvos").fetchall()
    return {linha["telefone"] for linha in linhas}


def adicionar_alvos(itens: list[dict]) -> int:
    if not itens:
        return 0
    criados = 0
    with _abrir(escrita=True) as con:
        for item in itens:
            cursor = con.execute(
                "INSERT OR IGNORE INTO alvos "
                "(assinatura_id, telefone, nome, primeiro_nome, produto, vencimento, texto, criado_em) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (
                    item["id"],
                    item["telefone"],
                    item.get("nome"),
                    item.get("primeiro_nome"),
                    item.get("produto"),
                    item.get("vencimento"),
                    item["texto"],
                    agora(),
                ),
            )
            criados += cursor.rowcount
    return criados


def fila(status: str | None = None) -> list[dict]:
    if not existe():
        return []
    sql = "SELECT * FROM alvos"
    parametros: list = []
    if status:
        sql += " WHERE status = ?"
        parametros.append(status)
    sql += " ORDER BY vencimento ASC, id ASC"
    with _abrir() as con:
        linhas = con.execute(sql, parametros).fetchall()
    return [dict(linha) for linha in linhas]


def limpar_pendentes() -> int:
    if not existe():
        return 0
    with _abrir(escrita=True) as con:
        cursor = con.execute("DELETE FROM alvos WHERE status = 'pendente'")
        con.execute(
            "UPDATE pedidos SET situacao = 'cancelado', atendido_em = ? "
            "WHERE situacao = 'pendente'",
            (agora(),),
        )
        return cursor.rowcount


def remover_pendentes_do_telefone(telefone: str) -> int:
    if not existe():
        return 0
    with _abrir(escrita=True) as con:
        cursor = con.execute(
            "DELETE FROM alvos WHERE telefone = ? AND status = 'pendente'", (telefone,)
        )
        return cursor.rowcount


def remover_alvo(alvo_id: int) -> bool:
    if not existe():
        return False
    with _abrir(escrita=True) as con:
        cursor = con.execute(
            "DELETE FROM alvos WHERE id = ? AND status = 'pendente'", (alvo_id,)
        )
        if cursor.rowcount:
            con.execute(
                "UPDATE pedidos SET situacao = 'cancelado', atendido_em = ? "
                "WHERE alvo_id = ? AND situacao = 'pendente'",
                (agora(), alvo_id),
            )
        return cursor.rowcount > 0


def alvo(alvo_id: int) -> dict | None:
    if not existe():
        return None
    with _abrir() as con:
        linha = con.execute("SELECT * FROM alvos WHERE id = ?", (alvo_id,)).fetchone()
    return dict(linha) if linha else None


def marcar_enviando(alvo_id: int) -> bool:
    """Reserva o alvo para o conector. So funciona se ainda estiver pendente."""
    if not existe():
        return False
    with _abrir(escrita=True) as con:
        cursor = con.execute(
            "UPDATE alvos SET status = 'enviando', atualizado_em = ? "
            "WHERE id = ? AND status = 'pendente'",
            (agora(), alvo_id),
        )
        return cursor.rowcount > 0


def cancelar_alvo(alvo_id: int, motivo: str = "") -> bool:
    """Tira o alvo da fila sem marcar envio (opt-out, cooldown, remetente)."""
    if not existe():
        return False
    with _abrir(escrita=True) as con:
        cursor = con.execute(
            "UPDATE alvos SET status = 'cancelado', atualizado_em = ? "
            "WHERE id = ? AND status IN ('pendente','enviando')",
            (agora(), alvo_id),
        )
        if cursor.rowcount:
            con.execute(
                "UPDATE pedidos SET situacao = 'cancelado', atendido_em = ? "
                "WHERE alvo_id = ? AND situacao = 'pendente'",
                (agora(), alvo_id),
            )
        return cursor.rowcount > 0


def devolver_alvo(alvo_id: int) -> bool:
    """Desfaz a reserva (simulacao, Ctrl+C, duvida do operador)."""
    if not existe():
        return False
    with _abrir(escrita=True) as con:
        cursor = con.execute(
            "UPDATE alvos SET status = 'pendente', atualizado_em = ? "
            "WHERE id = ? AND status = 'enviando'",
            (agora(), alvo_id),
        )
        return cursor.rowcount > 0


def reabrir_alvo(alvo_id: int) -> bool:
    """Devolve um alvo em 'falha' para a fila (quando ainda ha tentativas)."""
    if not existe():
        return False
    with _abrir(escrita=True) as con:
        cursor = con.execute(
            "UPDATE alvos SET status = 'pendente', atualizado_em = ? "
            "WHERE id = ? AND status = 'falha'",
            (agora(), alvo_id),
        )
        return cursor.rowcount > 0


def liberar_reservas_expiradas(minutos: int | None = None) -> int:
    """Devolve para 'pendente' o que ficou reservado alem do tempo."""
    minutos = config.CONECTOR_RESERVA_MINUTOS if minutos is None else minutos
    if not existe():
        return 0
    limite = (_momento() - timedelta(minutes=minutos)).strftime("%Y-%m-%d %H:%M:%S")
    with _abrir(escrita=True) as con:
        cursor = con.execute(
            "UPDATE alvos SET status = 'pendente', atualizado_em = ? "
            "WHERE status = 'enviando' AND (atualizado_em IS NULL OR atualizado_em < ?)",
            (agora(), limite),
        )
        return cursor.rowcount


# ------------------------------ envio manual -------------------------------

def criar_pedido(alvo_id: int) -> dict | None:
    """Anota um pedido de envio manual para um alvo pendente (1 por alvo)."""
    item = alvo(alvo_id)
    if not item or item["status"] != "pendente":
        return None
    with _abrir(escrita=True) as con:
        aberto = con.execute(
            "SELECT * FROM pedidos WHERE alvo_id = ? AND situacao = 'pendente' "
            "ORDER BY id ASC LIMIT 1",
            (alvo_id,),
        ).fetchone()
        if aberto:
            return dict(aberto)
        cursor = con.execute(
            "INSERT INTO pedidos (alvo_id, criado_em) VALUES (?,?)",
            (alvo_id, agora()),
        )
        linha = con.execute(
            "SELECT * FROM pedidos WHERE id = ?", (cursor.lastrowid,)
        ).fetchone()
    return dict(linha) if linha else None


def pedidos_abertos() -> dict[int, dict]:
    if not existe():
        return {}
    with _abrir() as con:
        linhas = con.execute(
            "SELECT * FROM pedidos WHERE situacao = 'pendente' ORDER BY id ASC"
        ).fetchall()
    return {linha["alvo_id"]: dict(linha) for linha in linhas}


def proximo_pedido() -> dict | None:
    """Pedido mais antigo cujo alvo ainda esta pendente."""
    if not existe():
        return None
    with _abrir() as con:
        linha = con.execute(
            "SELECT p.* FROM pedidos p JOIN alvos a ON a.id = p.alvo_id "
            "WHERE p.situacao = 'pendente' AND a.status = 'pendente' "
            "ORDER BY p.id ASC LIMIT 1"
        ).fetchone()
    return dict(linha) if linha else None


def atender_pedido_do_alvo(alvo_id: int, situacao: str = "enviado") -> int:
    if not existe():
        return 0
    with _abrir(escrita=True) as con:
        cursor = con.execute(
            "UPDATE pedidos SET situacao = ?, atendido_em = ? "
            "WHERE alvo_id = ? AND situacao = 'pendente'",
            ((situacao or "enviado")[:20], agora(), alvo_id),
        )
        return cursor.rowcount


def cancelar_pedido(alvo_id: int) -> bool:
    return atender_pedido_do_alvo(alvo_id, "cancelado") > 0


# -------------------------------- envios ----------------------------------

def registrar_envio(
    telefone: str,
    texto: str,
    situacao: str,
    alvo_id: int | None = None,
    erro: str | None = None,
) -> int:
    with _abrir(escrita=True) as con:
        cursor = con.execute(
            "INSERT INTO envios (alvo_id, telefone, texto, situacao, erro, criado_em) "
            "VALUES (?,?,?,?,?,?)",
            (alvo_id, telefone, texto, situacao, erro, agora()),
        )
        if alvo_id is not None:
            con.execute(
                "UPDATE alvos SET status = ?, tentativas = tentativas + 1, atualizado_em = ? "
                "WHERE id = ?",
                (situacao, agora(), alvo_id),
            )
        return int(cursor.lastrowid)


def envios(limite: int = 200) -> list[dict]:
    if not existe():
        return []
    with _abrir() as con:
        linhas = con.execute(
            "SELECT * FROM envios ORDER BY id DESC LIMIT ?", (limite,)
        ).fetchall()
    return [dict(linha) for linha in linhas]


def envios_do_dia(dia: str) -> int:
    """Quantos envios reais sairam no dia (formato AAAA-MM-DD)."""
    if not existe():
        return 0
    with _abrir() as con:
        total = con.execute(
            "SELECT count(*) FROM envios WHERE situacao IN (?,?) "
            "AND substr(criado_em, 1, 10) = ?",
            (*config.SITUACOES_ENVIADO, dia),
        ).fetchone()[0]
    return int(total)


def dias_com_envio() -> set[str]:
    """Dias distintos que ja tiveram envio (para calcular a rampa)."""
    if not existe():
        return set()
    with _abrir() as con:
        linhas = con.execute(
            "SELECT DISTINCT substr(criado_em, 1, 10) FROM envios "
            "WHERE situacao IN (?,?)",
            config.SITUACOES_ENVIADO,
        ).fetchall()
    return {linha[0] for linha in linhas}


def proximo_envio_em() -> str:
    return _ler_estado("proximo_envio_em", "")


def definir_proximo_envio(valor: str) -> None:
    _gravar_estado("proximo_envio_em", valor)


# --------------------------------- estado ---------------------------------

def _ler_estado(chave: str, padrao: str = "") -> str:
    if not existe():
        return padrao
    with _abrir() as con:
        linha = con.execute("SELECT valor FROM estado WHERE chave = ?", (chave,)).fetchone()
    return linha["valor"] if linha else padrao


def _gravar_estado(chave: str, valor: str) -> None:
    with _abrir(escrita=True) as con:
        con.execute(
            "INSERT INTO estado (chave, valor, atualizado_em) VALUES (?,?,?) "
            "ON CONFLICT(chave) DO UPDATE SET valor=excluded.valor, "
            "atualizado_em=excluded.atualizado_em",
            (chave, valor, agora()),
        )


def campanha_ativa() -> bool:
    return _ler_estado("ativa", "0") == "1"


def ativar() -> None:
    _gravar_estado("ativa", "1")
    _gravar_estado("motivo_pausa", "")
    # Reativar Ã© decisÃ£o do operador: zera a sequÃªncia que causou a pausa.
    _gravar_estado("falhas_consecutivas", "0")


def pausar(motivo: str = "") -> None:
    _gravar_estado("ativa", "0")
    _gravar_estado("motivo_pausa", (motivo or "").strip()[:200])


def motivo_pausa() -> str:
    return _ler_estado("motivo_pausa", "")


def falhas_consecutivas() -> int:
    try:
        return max(0, int(_ler_estado("falhas_consecutivas", "0") or 0))
    except ValueError:
        return 0


def registrar_falha_consecutiva(erro: str) -> int:
    """Conta falhas de envio em sequencia e guarda o ultimo erro."""
    total = falhas_consecutivas() + 1
    _gravar_estado("falhas_consecutivas", str(total))
    _gravar_estado("ultimo_erro", (erro or "").strip()[:300])
    _gravar_estado("ultimo_erro_em", agora())
    return total


def zerar_falhas_consecutivas() -> None:
    _gravar_estado("falhas_consecutivas", "0")


def ultimo_erro() -> str:
    return _ler_estado("ultimo_erro", "")


def ultimo_erro_em() -> str:
    return _ler_estado("ultimo_erro_em", "")


def erros_worker() -> int:
    try:
        return max(0, int(_ler_estado("erros_worker", "0") or 0))
    except ValueError:
        return 0


def registrar_erro_worker(motivo: str) -> int:
    """Erro fatal do braco (desconexao, auth): guarda e devolve o total."""
    total = erros_worker() + 1
    _gravar_estado("erros_worker", str(total))
    _gravar_estado("ultimo_erro_worker", (motivo or "").strip()[:300])
    _gravar_estado("ultimo_erro_worker_em", agora())
    return total


def ultimo_erro_worker() -> str:
    return _ler_estado("ultimo_erro_worker", "")


def ultimo_erro_worker_em() -> str:
    return _ler_estado("ultimo_erro_worker_em", "")


def registrar_ultimo_erro(erro: str) -> None:
    """Guarda o erro sem contar falha (ex.: numero que nao existe)."""
    _gravar_estado("ultimo_erro", (erro or "").strip()[:300])
    _gravar_estado("ultimo_erro_em", agora())


# --------------------------- contatos do WhatsApp ---------------------------

def salvar_contatos_whatsapp(itens: list[dict]) -> int:
    """Grava/atualiza a lista de contatos enviada pelo worker."""
    if not itens:
        return 0
    momento = agora()
    salvos = 0
    with _abrir(escrita=True) as con:
        for item in itens:
            telefone = (item.get("telefone") or "").strip()
            if not telefone:
                continue
            con.execute(
                "INSERT INTO contatos_whatsapp (telefone, nome, atualizado_em) "
                "VALUES (?,?,?) ON CONFLICT(telefone) DO UPDATE SET "
                "nome = excluded.nome, atualizado_em = excluded.atualizado_em",
                (telefone, (item.get("nome") or "").strip()[:120], momento),
            )
            salvos += 1
    return salvos


def contatos_whatsapp(limite: int = 20000) -> list[dict]:
    if not existe():
        return []
    with _abrir() as con:
        linhas = con.execute(
            "SELECT telefone, nome, atualizado_em FROM contatos_whatsapp "
            "ORDER BY nome COLLATE NOCASE, telefone LIMIT ?",
            (limite,),
        ).fetchall()
    return [dict(linha) for linha in linhas]


def resumo_contatos_whatsapp() -> dict:
    if not existe():
        return {"total": 0, "atualizado_em": ""}
    with _abrir() as con:
        linha = con.execute(
            "SELECT count(*) AS total, coalesce(max(atualizado_em),'') AS atualizado_em "
            "FROM contatos_whatsapp"
        ).fetchone()
    return {"total": int(linha["total"]), "atualizado_em": linha["atualizado_em"]}


def pedir_contatos() -> str:
    """Marca um pedido de lista; o worker ve no proximo pulso e responde."""
    momento = agora()
    _gravar_estado("contatos_pedido", momento)
    _gravar_estado("contatos_completo_em", "")
    return momento


def marcar_contatos_completos() -> str:
    momento = agora()
    _gravar_estado("contatos_completo_em", momento)
    return momento


def contatos_completos_em() -> str:
    return _ler_estado("contatos_completo_em", "")


def consumir_pedido_contatos() -> bool:
    """Devolve True uma unica vez para o pedido pendente (expira em 10 min)."""
    valor = _ler_estado("contatos_pedido", "")
    if not valor:
        return False
    _gravar_estado("contatos_pedido", "")
    try:
        quando = datetime.strptime(valor, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return False
    return (_momento() - quando).total_seconds() <= 600


def registrar_worker(modo: str, pid: int | None = None) -> None:
    """Batimento do worker: diz que esta vivo, em qual modo e com qual PID."""
    _gravar_estado("worker_modo", (modo or "").strip()[:20])
    _gravar_estado("worker_visto_em", agora())
    if pid:
        _gravar_estado("worker_pid", str(int(pid)))


def salvar_worker_pid(pid: int) -> None:
    _gravar_estado("worker_pid", str(int(pid)))


def worker_pid() -> int:
    try:
        return int(_ler_estado("worker_pid", "0") or 0)
    except ValueError:
        return 0


def limpar_worker() -> None:
    """Esquece o worker: some com o PID e com o batimento (fica offline na hora)."""
    _gravar_estado("worker_pid", "")
    _gravar_estado("worker_modo", "")
    _gravar_estado("worker_visto_em", "")


def pedir_parada_worker() -> str:
    """Marca um pedido de encerramento; o worker ve no proximo pulso."""
    momento = agora()
    _gravar_estado("worker_parar", momento)
    return momento


def limpar_pedido_parada() -> None:
    _gravar_estado("worker_parar", "")


def consumir_pedido_parada() -> bool:
    """True uma unica vez para o pedido pendente (expira em 2 min)."""
    valor = _ler_estado("worker_parar", "")
    if not valor:
        return False
    _gravar_estado("worker_parar", "")
    try:
        quando = datetime.strptime(valor, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return False
    return (_momento() - quando).total_seconds() <= 120


def worker_status(segundos: int = 45) -> dict:
    modo = _ler_estado("worker_modo", "")
    visto = _ler_estado("worker_visto_em", "")
    online = False
    if visto:
        try:
            quando = datetime.strptime(visto, "%Y-%m-%d %H:%M:%S")
            online = (_momento() - quando).total_seconds() <= segundos
        except ValueError:
            online = False
    return {
        "online": online,
        "modo": modo if online else "",
        "ultimo_modo": modo,
        "visto_em": visto,
        "pid": worker_pid(),
    }


def numero_remetente_salvo() -> str:
    return _ler_estado("numero_remetente", "")


def salvar_numero_remetente(numero: str) -> None:
    _gravar_estado("numero_remetente", numero)


def numero_conectado() -> str:
    """Numero que o worker informou estar pareado (ultimo visto)."""
    return _ler_estado("numero_conectado", "")


def salvar_numero_conectado(numero: str) -> None:
    _gravar_estado("numero_conectado", (numero or "").strip()[:20])


def numero_teste_salvo() -> str:
    return _ler_estado("numero_teste", "")


def salvar_numero_teste(numero: str) -> None:
    _gravar_estado("numero_teste", numero)


def parametros_salvos() -> str:
    return _ler_estado("parametros", "")


def salvar_parametros_json(valor: str) -> None:
    _gravar_estado("parametros", valor)


def limpar_parametros() -> None:
    if not existe():
        return
    with _abrir(escrita=True) as con:
        con.execute("DELETE FROM estado WHERE chave = 'parametros'")


def metricas() -> dict:
    if not existe():
        return {"total": 0, "pendentes": 0, "enviados": 0, "falhas": 0, "optouts": 0}
    with _abrir() as con:
        total = con.execute("SELECT count(*) FROM alvos").fetchone()[0]
        pendentes = con.execute(
            "SELECT count(*) FROM alvos WHERE status = 'pendente'"
        ).fetchone()[0]
        enviados = con.execute(
            "SELECT count(*) FROM envios WHERE situacao IN (?,?)",
            config.SITUACOES_ENVIADO,
        ).fetchone()[0]
        falhas = con.execute(
            "SELECT count(*) FROM envios WHERE situacao = 'falha'"
        ).fetchone()[0]
        bloqueados = con.execute("SELECT count(*) FROM optouts").fetchone()[0]
    return {
        "total": int(total),
        "pendentes": int(pendentes),
        "enviados": int(enviados),
        "falhas": int(falhas),
        "optouts": int(bloqueados),
    }
