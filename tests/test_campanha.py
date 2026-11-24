"""Testes isolados da campanha.

Usam uma base de assinaturas FALSA (criada em diretorio temporario) e o banco
da campanha tambem temporario. Nada toca em dados/assinaturas.db real.
"""

import json
import os
import sqlite3
import tempfile
from datetime import date, datetime
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="campanha-teste-"))
_BANCO_ASSINATURAS = _TMP / "assinaturas-falsa.db"
_BANCO_CAMPANHA = _TMP / "campanha-teste.db"
_SAIDA = _TMP / "lotes"

os.environ["CAMPANHA_BANCO_ASSINATURAS"] = str(_BANCO_ASSINATURAS)
os.environ["CAMPANHA_BANCO"] = str(_BANCO_CAMPANHA)
os.environ["CAMPANHA_MODO"] = "previa"
os.environ.setdefault("API_KEY", "chave-campanha")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.campanha import armazenamento, config, contatos, humanizacao, mensagens, optout  # noqa: E402
from app.campanha import midia, planilha, selecao, servico, worker_local  # noqa: E402
from app.campanha import conector  # noqa: E402
from app.main import app  # noqa: E402
from app.security import API_KEY as CHAVE_ATIVA  # noqa: E402

# Garante que os testes usem os bancos temporarios mesmo que app.* ja tenha
# sido importado por outro modulo de teste (os modulos leem em tempo de uso).
config.BANCO_ASSINATURAS = _BANCO_ASSINATURAS
config.BANCO_CAMPANHA = _BANCO_CAMPANHA
config.PASTA_SAIDA = _SAIDA
config.LOG_WORKER = _TMP / "campanha-worker.log"
config.MODO = "previa"

HEADERS = {"X-API-Key": CHAVE_ATIVA}
cliente = TestClient(app)


def _criar_base_falsa():
    con = sqlite3.connect(_BANCO_ASSINATURAS)
    con.execute(
        """
        CREATE TABLE assinaturas (
            id INTEGER PRIMARY KEY,
            nome TEXT, usuario TEXT, contato TEXT, status TEXT,
            vencimento TEXT, produto TEXT, plano_nome TEXT, valor_final REAL
        )
        """
    )
    linhas = [
        (1, "8DEBORA", "8DEBORA", "11999998888", "INATIVO", "2024-05-10", "IPTV", "IPTV 1", 20.0),
        (2, "LUCAS", "LUCAS54X", "(11) 98888-7777", "INATIVO", "2024-06-01", "INTERNET", "NET", 30.0),
        (3, "SEM FONE", None, "", "INATIVO", "2024-01-01", "IPTV", "IPTV 1", 20.0),
        (4, "CANCELADO", None, "11977776666", "CANCELADO", "2024-01-01", "IPTV", "IPTV 1", 20.0),
        (5, "ATIVO", None, "11966665555", "ATIVO", "2026-12-01", "IPTV", "IPTV 1", 20.0),
        (6, "DUPLICADO", None, "11999998888", "SUSPENSO", "2024-07-01", "INTERNET", "NET", 30.0),
        (7, "FIXO", None, "1133334444", "INATIVO", "2024-02-02", "IPTV", "IPTV 1", 20.0),
        (8, "INVALIDO", None, "123", "INATIVO", "2024-02-02", "IPTV", "IPTV 1", 20.0),
        (9, "REMETENTE", None, "11992501859", "INATIVO", "2024-03-03", "IPTV", "IPTV 1", 20.0),
    ]
    con.executemany(
        "INSERT INTO assinaturas (id, nome, usuario, contato, status, vencimento, produto, plano_nome, valor_final) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        linhas,
    )
    con.commit()
    con.close()


_criar_base_falsa()


@pytest.fixture(autouse=True)
def banco_da_campanha_limpo():
    if _BANCO_CAMPANHA.exists():
        _BANCO_CAMPANHA.unlink()
    yield


# ------------------------------- unidades ---------------------------------

def test_normalizar_telefone():
    assert contatos.normalizar("11999998888") == "5511999998888"
    assert contatos.normalizar("(11) 98888-7777") == "5511988887777"
    assert contatos.normalizar("1133334444") == "551133334444"
    assert contatos.normalizar("+55 11 99999-8888") == "5511999998888"
    assert contatos.normalizar("123") is None
    assert contatos.normalizar("Debora") is None
    assert contatos.normalizar("") is None


def test_primeiro_nome():
    assert contatos.primeiro_nome("8DEBORA") == "Debora"
    assert contatos.primeiro_nome(None, "LUCAS54X") == "Lucas"
    assert contatos.primeiro_nome("maria aparecida") == "Maria"
    assert contatos.primeiro_nome("") == ""


def test_mensagem_tem_nome_e_saida():
    texto = mensagens.renderizar(mensagens.PADRAO, "8DEBORA", "8DEBORA")
    assert "Debora" in texto
    assert "SAIR" in texto
    assert "{nome}" not in texto


def test_mensagem_sem_nome_nao_deixa_placeholder():
    texto = mensagens.renderizar(mensagens.PADRAO, "", "")
    assert "{nome}" not in texto
    assert texto.startswith("Olá!")
    assert "SAIR" in texto


def test_optout_detecta_recusa():
    assert optout.detectar("sair") == "optout"
    assert optout.detectar("não me mande mais mensagens") == "optout"
    assert optout.detectar("quero ser removido") == "optout"
    assert optout.detectar("não tenho interesse") == "recusa"
    assert optout.detectar("quero saber mais do teste") is None


def test_humanizacao_limites():
    assert config.INTERVALO_MIN <= humanizacao.intervalo_entre_envios() <= config.INTERVALO_MAX
    for _ in range(50):
        atraso = humanizacao.calcular("texto curto")
        assert humanizacao.DIGITACAO_MIN <= atraso <= humanizacao.DIGITACAO_TETO


# -------------------------------- servico ---------------------------------

def test_elegiveis_conta_motivos():
    dados = servico.elegiveis()
    assert dados["disponivel"] is True
    assert dados["resumo"]["lidos"] == 7
    assert dados["resumo"]["sem_telefone"] == 2
    assert dados["resumo"]["repetido"] == 1
    assert dados["resumo"]["remetente"] == 1
    assert dados["total"] == 3
    ids = sorted(item["id"] for item in dados["itens"])
    assert ids == [1, 2, 7]


def test_numero_remetente_configurado():
    assert config.numero_remetente() == "5511992501859"
    assert all(item["telefone"] != config.numero_remetente() for item in servico.elegiveis()["itens"])


def test_elegiveis_filtra_por_produto():
    dados = servico.elegiveis(produto="IPTV")
    assert sorted(item["id"] for item in dados["itens"]) == [1, 7]


def test_apenas_unicos_exclui_numero_compartilhado():
    dados = servico.elegiveis(apenas_unicos=True)
    assert dados["resumo"]["compartilhado"] == 1
    assert sorted(item["id"] for item in dados["itens"]) == [2, 7]


def test_compartilhados_agrupa_por_numero():
    grupos = servico.compartilhados(minimo=2)
    assert len(grupos) == 1
    assert grupos[0]["telefone"] == "5511999998888"
    assert grupos[0]["total"] == 2
    assert sorted(c["id"] for c in grupos[0]["clientes"]) == [1, 6]


def test_produtos_da_base():
    lista = selecao.produtos()
    nomes = {item["produto"] for item in lista}
    assert "IPTV" in nomes and "INTERNET" in nomes


def test_previa_nao_grava_nada():
    dados = servico.previa(limite=5, variar=True)
    assert len(dados["itens"]) == 3
    assert all("SAIR" in item["texto"] for item in dados["itens"])
    assert armazenamento.existe() is False


def test_criar_fila_e_plano():
    resultado = servico.criar_fila(limite=500, variar=False)
    assert resultado["criados"] == 3
    assert len(armazenamento.fila("pendente")) == 3
    plano = servico.plano()
    assert plano["total"] == 3
    assert plano["dias"][0]["quantidade"] == 3


def test_optout_remove_da_fila():
    servico.criar_fila(limite=500, variar=False)
    assert armazenamento.bloquear("5511999998888", motivo="teste", origem="teste")
    removidos = armazenamento.remover_pendentes_do_telefone("5511999998888")
    assert removidos == 1
    assert len(armazenamento.fila("pendente")) == 2
    restantes = servico.elegiveis()
    assert all(item["telefone"] != "5511999998888" for item in restantes["itens"])


# --------------------------------- API ------------------------------------

def test_api_exige_chave():
    assert cliente.get("/campanha/config").status_code == 401


def test_api_config_mostra_modo_previa():
    resposta = cliente.get("/campanha/config", headers=HEADERS)
    assert resposta.status_code == 200
    dados = resposta.json()
    assert dados["modo"] == "previa"
    assert dados["envio_ativo"] is False
    assert dados["ativa"] is False
    assert dados["numero_remetente"] == "5511992501859"
    assert dados["numero_remetente_padrao"] == "5511992501859"


def test_api_troca_numero_remetente():
    resposta = cliente.post(
        "/campanha/numero", headers=HEADERS, json={"numero": "(11) 98888-7777"}
    )
    assert resposta.status_code == 200
    assert resposta.json()["numero_remetente"] == "5511988887777"

    configuracao = cliente.get("/campanha/config", headers=HEADERS).json()
    assert configuracao["numero_remetente"] == "5511988887777"
    assert configuracao["numero_remetente_padrao"] == "5511992501859"


def test_api_numero_invalido():
    resposta = cliente.post("/campanha/numero", headers=HEADERS, json={"numero": "abc"})
    assert resposta.status_code == 422


def test_numero_teste_fica_fora_da_fila():
    troca = cliente.post(
        "/campanha/numero", headers=HEADERS, json={"teste": "(11) 98888-7777"}
    )
    assert troca.status_code == 200
    assert troca.json()["numero_teste"] == "5511988887777"

    dados = servico.elegiveis()
    assert dados["resumo"]["teste"] == 1
    assert all(item["id"] != 2 for item in dados["itens"])
    assert dados["total"] == 2


def test_api_exportar_lote_nao_altera_fila():
    cliente.post("/campanha/fila", headers=HEADERS, json={"limite": 500})
    resposta = cliente.post("/campanha/exportar?limite=10", headers=HEADERS)
    assert resposta.status_code == 200
    dados = resposta.json()
    assert dados["quantidade"] == 3

    caminho = Path(dados["arquivo"])
    assert caminho.exists()
    linhas = caminho.read_text(encoding="utf-8").strip().splitlines()
    assert len(linhas) == 3
    assert "SAIR" in json.loads(linhas[0])["texto"]

    fila = cliente.get("/campanha/fila", headers=HEADERS).json()
    assert len(fila["itens"]) == 3


def test_api_exportar_fila_vazia():
    resposta = cliente.post("/campanha/exportar", headers=HEADERS)
    assert resposta.status_code == 409


def test_api_compartilhados():
    resposta = cliente.get("/campanha/compartilhados?minimo=2", headers=HEADERS)
    assert resposta.status_code == 200
    dados = resposta.json()
    assert dados["total_numeros"] == 1
    assert dados["total_clientes"] == 2


def test_api_remover_alvo_da_fila():
    cliente.post("/campanha/fila", headers=HEADERS, json={"limite": 500})
    fila = cliente.get("/campanha/fila", headers=HEADERS).json()["itens"]
    removido = cliente.delete(f"/campanha/fila/{fila[0]['id']}", headers=HEADERS)
    assert removido.status_code == 200
    assert len(cliente.get("/campanha/fila", headers=HEADERS).json()["itens"]) == 2
    assert cliente.delete(f"/campanha/fila/{fila[0]['id']}", headers=HEADERS).status_code == 404


def test_api_elegiveis():
    resposta = cliente.get("/campanha/elegiveis?limite=10", headers=HEADERS)
    assert resposta.status_code == 200
    assert resposta.json()["total"] == 3


def test_api_previa_e_fila():
    previa = cliente.post("/campanha/previa", headers=HEADERS, json={"limite": 3, "variar": True})
    assert previa.status_code == 200
    assert len(previa.json()["itens"]) == 3

    fila = cliente.post("/campanha/fila", headers=HEADERS, json={"limite": 500, "variar": True})
    assert fila.status_code == 201
    assert fila.json()["criados"] == 3

    listagem = cliente.get("/campanha/fila", headers=HEADERS)
    assert len(listagem.json()["itens"]) == 3

    plano = cliente.get("/campanha/plano", headers=HEADERS)
    assert plano.json()["total"] == 3

    limpeza = cliente.delete("/campanha/fila", headers=HEADERS)
    assert limpeza.json()["removidos"] == 3


def test_api_optout_e_remocao():
    criado = cliente.post(
        "/campanha/optouts", headers=HEADERS, json={"telefone": "11999998888", "motivo": "pediu"}
    )
    assert criado.status_code == 201
    assert criado.json()["telefone"] == "5511999998888"

    lista = cliente.get("/campanha/optouts", headers=HEADERS)
    assert lista.json()["total"] == 1

    removido = cliente.delete("/campanha/optouts/5511999998888", headers=HEADERS)
    assert removido.status_code == 200
    assert cliente.get("/campanha/optouts", headers=HEADERS).json()["total"] == 0


def test_api_ativar_bloqueado_em_previa(monkeypatch):
    monkeypatch.setattr(config, "ENVIO_REAL_HABILITADO", True)
    monkeypatch.setattr(config, "MODO", "previa")
    cliente.post("/campanha/fila", headers=HEADERS, json={"limite": 500})
    resposta = cliente.post("/campanha/ativar", headers=HEADERS)
    assert resposta.status_code == 409
    assert "modo previa" in resposta.json()["detail"].lower()


def test_api_ativar_bloqueado_pela_trava(monkeypatch):
    monkeypatch.setattr(config, "ENVIO_REAL_HABILITADO", False)
    monkeypatch.setattr(config, "MODO", "real")
    cliente.post("/campanha/fila", headers=HEADERS, json={"limite": 500})
    resposta = cliente.post("/campanha/ativar", headers=HEADERS, json={"confirmo": "ENVIAR"})
    assert resposta.status_code == 409
    assert "trava" in resposta.json()["detail"].lower()


def test_api_ativar_bloqueado_mesmo_em_modo_arquivo(monkeypatch):
    monkeypatch.setattr(config, "ENVIO_REAL_HABILITADO", True)
    monkeypatch.setattr(config, "MODO", "arquivo")
    cliente.post("/campanha/fila", headers=HEADERS, json={"limite": 500})
    resposta = cliente.post("/campanha/ativar", headers=HEADERS)
    assert resposta.status_code == 409
    assert "modo arquivo" in resposta.json()["detail"].lower()


def test_api_pausar_funciona():
    resposta = cliente.post("/campanha/pausar", headers=HEADERS, json={"motivo": "teste"})
    assert resposta.status_code == 200
    assert resposta.json()["ativa"] is False


# --- Midia (fase 2): apenas catalogo local, nada e enviado ------------------


@pytest.fixture()
def pasta_midia(tmp_path, monkeypatch):
    pasta = tmp_path / "midia"
    pasta.mkdir()
    monkeypatch.setattr(config, "MIDIA_PASTA", pasta)
    return pasta


def test_midia_nasce_desligada_e_sem_primeiro_contato():
    assert config.MIDIA_HABILITADA is False
    assert config.MIDIA_NO_PRIMEIRO_CONTATO is False


def test_midia_lista_pasta_vazia(pasta_midia):
    dados = midia.listar()
    assert dados["total"] == 0
    assert dados["habilitada"] is False
    assert dados["itens"] == []


def test_midia_validar_png_pequeno(pasta_midia):
    arquivo = pasta_midia / "flyer.png"
    arquivo.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 2000)
    dados = midia.validar(arquivo)
    assert dados["ok"] is True
    assert dados["formato"] == "png"


def test_midia_validar_recusa_formato_nao_aprovado(pasta_midia):
    arquivo = pasta_midia / "flyer.gif"
    arquivo.write_bytes(b"0" * 100)
    dados = midia.validar(arquivo)
    assert dados["ok"] is False
    assert "formato" in dados["motivo"]


def test_midia_validar_recusa_arquivo_grande(pasta_midia):
    arquivo = pasta_midia / "grande.jpg"
    arquivo.write_bytes(b"0" * (3 * 1024 * 1024))
    dados = midia.validar(arquivo)
    assert dados["ok"] is False
    assert "acima do limite" in dados["motivo"]


def test_midia_listar_ignora_extensao_nao_aprovada(pasta_midia):
    (pasta_midia / "flyer.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 100)
    (pasta_midia / "notas.txt").write_text("nao e imagem", encoding="utf-8")
    dados = midia.listar()
    assert dados["total"] == 1
    assert dados["itens"][0]["arquivo"] == "flyer.png"


def test_midia_resolver_bloqueia_caminho_fora_da_pasta(pasta_midia):
    assert midia.resolver("../assinaturas.db") is None
    assert midia.resolver("..\\assinaturas.db") is None
    assert midia.resolver("") is None
    assert midia.resolver(".oculto.png") is None
    assert midia.resolver("nao-existe.png") is None


def test_midia_resolver_devolve_arquivo_da_pasta(pasta_midia):
    arquivo = pasta_midia / "flyer.jpg"
    arquivo.write_bytes(b"\xff\xd8\xff" + b"0" * 100)
    assert midia.resolver("flyer.jpg") == arquivo


def test_legenda_do_flyer_tem_optout():
    dados = midia.legenda()
    assert "SAIR" in dados["texto"].upper()
    assert dados["ok"] is True
    assert dados["caracteres"] <= config.MIDIA_LIMITE_LEGENDA


def test_legenda_do_flyer_garante_optout_quando_falta():
    dados = midia.legenda(texto="Segue o flyer.")
    assert dados["texto"].startswith("Segue o flyer.")
    assert "SAIR" in dados["texto"].upper()


def test_api_midias_somente_leitura(pasta_midia):
    resposta = cliente.get("/campanha/midias", headers=HEADERS)
    assert resposta.status_code == 200
    dados = resposta.json()
    assert dados["total"] == 0
    assert dados["habilitada"] is False
    assert dados["no_primeiro_contato"] is False
    assert "SAIR" in dados["legenda"]["texto"].upper()
    assert cliente.get("/campanha/midias/flyer.png", headers=HEADERS).status_code == 404


def test_api_midia_serve_imagem_da_pasta(pasta_midia):
    (pasta_midia / "flyer.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 100)
    resposta = cliente.get("/campanha/midias/flyer.png", headers=HEADERS)
    assert resposta.status_code == 200
    assert resposta.content.startswith(b"\x89PNG")


def test_api_config_expoe_midia_desligada():
    dados = cliente.get("/campanha/config", headers=HEADERS).json()
    assert dados["midia_habilitada"] is False
    assert dados["midia_no_primeiro_contato"] is False
    assert "SAIR" in dados["legenda_flyer"].upper()


# --- Conector (fase 2): cerebro do envio automatico -------------------------

SEGUNDA_10H = datetime(2026, 11, 16, 10, 0, 0)


@pytest.fixture()
def campanha_limpa():
    """Zera a fila/estado do banco temporario e remonta 3 alvos."""
    armazenamento.bloquear("5500000000000", motivo="prepara tabelas")
    con = sqlite3.connect(_BANCO_CAMPANHA)
    con.executescript(
        "DELETE FROM alvos; DELETE FROM envios; DELETE FROM optouts; DELETE FROM estado;"
        "DELETE FROM pedidos; DELETE FROM contatos_whatsapp;"
    )
    con.commit()
    con.close()
    cliente.post("/campanha/fila", headers=HEADERS, json={"limite": 500})
    return True


@pytest.fixture()
def conector_ligado(monkeypatch, campanha_limpa):
    """Trava liberada + modo real + relogio fixo numa segunda-feira 10h."""
    monkeypatch.setattr(config, "ENVIO_REAL_HABILITADO", True)
    monkeypatch.setattr(config, "MODO", "real")
    monkeypatch.setattr(config, "RESPEITAR_JANELAS", True)
    monkeypatch.setattr(conector, "_agora", lambda momento=None: momento or SEGUNDA_10H)
    # O banco tambem precisa do mesmo relogio: senao o dia do envio registrado
    # nao bate com o dia consultado pela cota quando o teste roda na virada.
    monkeypatch.setattr(armazenamento, "_momento", lambda: SEGUNDA_10H)
    armazenamento.ativar()
    return SEGUNDA_10H


def test_conector_bloqueado_pela_trava(campanha_limpa, monkeypatch):
    monkeypatch.setattr(config, "ENVIO_REAL_HABILITADO", False)
    dados = conector.estado(SEGUNDA_10H)
    assert dados["liberado"] is False
    assert dados["trava"] is True
    assert "trava" in dados["motivo"].lower()
    assert "numero_remetente" in dados and "numero_teste" in dados
    with pytest.raises(conector.Bloqueado):
        conector.reservar(SEGUNDA_10H)


def test_conector_bloqueia_fim_de_semana(conector_ligado):
    sabado = datetime(2026, 11, 21, 10, 0, 0)
    dados = conector.estado(sabado)
    assert dados["liberado"] is False
    assert "janela" in dados["motivo"]


def test_conector_bloqueia_fora_do_horario(conector_ligado):
    almoco = datetime(2026, 11, 16, 12, 0, 0)
    assert conector.estado(almoco)["liberado"] is False


def test_conector_reserva_um_alvo(conector_ligado):
    alvo = conector.reservar()
    assert alvo["telefone"].startswith("55")
    assert alvo["texto"]
    assert alvo["digitacao_segundos"] > 0
    assert armazenamento.alvo(alvo["alvo_id"])["status"] == "enviando"
    assert conector.estado()["reservados"] == 1


def test_conector_nao_reserva_dois_ao_mesmo_tempo(conector_ligado):
    primeiro = conector.reservar()
    segundo = conector.reservar()
    assert primeiro["alvo_id"] != segundo["alvo_id"]


def test_conector_confirmar_envio_grava_e_define_intervalo(conector_ligado):
    alvo = conector.reservar()
    dados = conector.confirmar(alvo["alvo_id"], "enviado")
    assert dados["situacao"] == "enviado"
    assert 90 <= dados["esperar_segundos"] <= 1200
    assert armazenamento.alvo(alvo["alvo_id"])["status"] == "enviado"
    assert armazenamento.envios_do_dia("2026-11-16") == 1
    seguinte = conector.estado()
    assert seguinte["liberado"] is False
    assert seguinte["esperar_segundos"] > 0


def test_conector_confirmar_falha_marca_alvo(conector_ligado):
    alvo = conector.reservar()
    dados = conector.confirmar(alvo["alvo_id"], "falha", erro="numero invalido")
    assert dados["situacao"] == "falha"
    assert armazenamento.alvo(alvo["alvo_id"])["status"] == "falha"
    assert armazenamento.envios_do_dia("2026-11-16") == 0


def test_conector_cota_do_dia_respeita_rampa(conector_ligado):
    for _ in range(10):
        armazenamento.registrar_envio("5511900000000", "texto", "enviado")
    dados = conector.estado()
    assert dados["cota_dia"] == 10
    assert dados["restante_hoje"] == 0
    assert "cota" in dados["motivo"]
    with pytest.raises(conector.Bloqueado):
        conector.reservar()


def test_conector_cota_sobe_com_dias_anteriores(conector_ligado):
    con = sqlite3.connect(_BANCO_CAMPANHA)
    con.executemany(
        "INSERT INTO envios (telefone, texto, situacao, criado_em) VALUES (?,?,?,?)",
        [
            ("5511900000000", "x", "enviado", "2026-11-12 10:00:00"),
            ("5511900000001", "x", "enviado", "2026-11-13 10:00:00"),
        ],
    )
    con.commit()
    con.close()
    assert conector.cota_do_dia(SEGUNDA_10H) == 30


def test_conector_pula_numero_em_optout(conector_ligado):
    fila = armazenamento.fila("pendente")
    escolhido = fila[0]
    armazenamento.bloquear(escolhido["telefone"], motivo="pediu para sair")
    alvo = conector.reservar()
    assert alvo["telefone"] != escolhido["telefone"]
    assert armazenamento.alvo(escolhido["id"])["status"] == "cancelado"


def test_reserva_expirada_volta_para_pendente(conector_ligado):
    alvo = conector.reservar()
    con = sqlite3.connect(_BANCO_CAMPANHA)
    con.execute(
        "UPDATE alvos SET atualizado_em = '2020-01-01 00:00:00' WHERE id = ?",
        (alvo["alvo_id"],),
    )
    con.commit()
    con.close()
    assert armazenamento.liberar_reservas_expiradas(15) == 1
    assert armazenamento.alvo(alvo["alvo_id"])["status"] == "pendente"


def test_api_conector_bloqueado_pela_trava(campanha_limpa, monkeypatch):
    monkeypatch.setattr(config, "ENVIO_REAL_HABILITADO", False)
    estado_api = cliente.get("/campanha/conector/estado", headers=HEADERS)
    assert estado_api.status_code == 200
    assert estado_api.json()["liberado"] is False
    resposta = cliente.post("/campanha/conector/proximo", headers=HEADERS)
    assert resposta.status_code == 409
    assert "trava" in resposta.json()["detail"]["motivo"].lower()


def test_api_conector_fluxo_liberado(conector_ligado):
    resposta = cliente.post("/campanha/conector/proximo", headers=HEADERS)
    assert resposta.status_code == 200
    alvo = resposta.json()
    confirmado = cliente.post(
        "/campanha/conector/confirmar",
        headers=HEADERS,
        json={"alvo_id": alvo["alvo_id"], "situacao": "enviado"},
    )
    assert confirmado.status_code == 200
    assert confirmado.json()["situacao"] == "enviado"
    estado_api = cliente.get("/campanha/conector/estado", headers=HEADERS).json()
    assert estado_api["enviados_hoje"] == 1
    assert estado_api["reservados"] == 0


def test_api_ativar_exige_confirmacao_no_modo_real(conector_ligado):
    assert cliente.post("/campanha/ativar", headers=HEADERS).status_code == 422
    resposta = cliente.post("/campanha/ativar", headers=HEADERS, json={"confirmo": "ENVIAR"})
    assert resposta.status_code == 200
    assert resposta.json()["ativa"] is True


def test_conector_devolver_nao_conta_como_envio(conector_ligado):
    alvo = conector.reservar()
    dados = conector.devolver(alvo["alvo_id"])
    assert dados["devolvido"] is True
    assert armazenamento.alvo(alvo["alvo_id"])["status"] == "pendente"
    assert armazenamento.envios_do_dia("2026-11-16") == 0
    assert conector.estado()["reservados"] == 0


def test_api_conector_devolver(conector_ligado):
    alvo = cliente.post("/campanha/conector/proximo", headers=HEADERS).json()
    resposta = cliente.post(
        "/campanha/conector/devolver", headers=HEADERS, json={"alvo_id": alvo["alvo_id"]}
    )
    assert resposta.status_code == 200
    assert resposta.json()["devolvido"] is True
    assert cliente.get("/campanha/conector/estado", headers=HEADERS).json()["enviados_hoje"] == 0


# --- Parametros de envio (painel) ------------------------------------------


def test_conector_modo_manual_ignora_horario(campanha_limpa, monkeypatch):
    monkeypatch.setattr(config, "ENVIO_REAL_HABILITADO", True)
    monkeypatch.setattr(config, "MODO", "real")
    monkeypatch.setattr(config, "RESPEITAR_JANELAS", False)
    monkeypatch.setattr(conector, "_agora", lambda momento=None: momento or SEGUNDA_10H)
    armazenamento.ativar()

    almoco = datetime(2026, 11, 16, 12, 0, 0)
    sabado = datetime(2026, 11, 21, 10, 0, 0)
    dados = conector.estado(almoco)
    assert dados["liberado"] is True
    assert dados["janelas_ativas"] is False
    assert "manual" in dados["janela_atual"]
    assert conector.estado(sabado)["liberado"] is True


def test_api_parametros_salva_e_aplica_no_conector(conector_ligado):
    resposta = cliente.post(
        "/campanha/parametros",
        headers=HEADERS,
        json={
            "cota_diaria": 3,
            "intervalo_min": 30,
            "intervalo_max": 60,
            "pausa_cada": 5,
            "pausa_min": 120,
            "pausa_max": 300,
            "cooldown_dias": 7,
            "max_tentativas": 2,
            "respeitar_janelas": True,
        },
    )
    assert resposta.status_code == 200
    dados = resposta.json()["parametros"]
    assert dados["cota_diaria"] == 3

    estado = conector.estado()
    assert estado["cota_dia"] == 3
    assert estado["cota_fixa"] == 3
    assert estado["intervalo"] == [30, 60]
    assert estado["pausa"] == [120, 300]
    assert estado["cooldown_dias"] == 7
    assert estado["max_tentativas"] == 2
    assert estado["janelas_ativas"] is True
    assert humanizacao.deve_pausar_longa(5) is True


def test_api_parametros_rejeita_intervalo_invertido(conector_ligado):
    resposta = cliente.post(
        "/campanha/parametros",
        headers=HEADERS,
        json={"intervalo_min": 200, "intervalo_max": 100},
    )
    assert resposta.status_code == 422
    assert "intervalo" in resposta.json()["detail"].lower()


def test_api_parametros_rejeita_valor_fora_da_faixa(conector_ligado):
    resposta = cliente.post(
        "/campanha/parametros", headers=HEADERS, json={"cota_diaria": 999}
    )
    assert resposta.status_code == 422


def test_api_parametros_restaura_padroes(conector_ligado):
    cliente.post(
        "/campanha/parametros", headers=HEADERS, json={"cota_diaria": 5, "cooldown_dias": 10}
    )
    assert conector.estado()["cota_dia"] == 5
    resposta = cliente.delete("/campanha/parametros", headers=HEADERS)
    assert resposta.status_code == 200
    padroes = resposta.json()["parametros"]
    assert padroes["cota_diaria"] == 0
    assert padroes["cooldown_dias"] == config.COOLDOWN_DIAS
    assert conector.estado()["cota_dia"] == config.RAMPA[0]


def test_conector_repete_falha_quando_tentativas_maior(conector_ligado):
    cliente.post(
        "/campanha/parametros", headers=HEADERS, json={"max_tentativas": 2}
    )
    alvo = conector.reservar()
    primeira = conector.confirmar(alvo["alvo_id"], "falha", erro="instavel")
    assert primeira["reaberto"] is True
    assert armazenamento.alvo(alvo["alvo_id"])["status"] == "pendente"

    segunda = conector.confirmar(alvo["alvo_id"], "falha", erro="instavel de novo")
    assert segunda["reaberto"] is False
    assert armazenamento.alvo(alvo["alvo_id"])["status"] == "falha"


# --- Pausa automatica e saude do envio --------------------------------------


def test_conector_pausa_automatica_apos_falhas(conector_ligado):
    cliente.post(
        "/campanha/parametros", headers=HEADERS, json={"max_falhas_seguidas": 2}
    )
    alvo = conector.reservar()
    primeira = conector.confirmar(alvo["alvo_id"], "falha", erro="ack 0")
    assert primeira["pausa_automatica"] is False
    assert conector.estado()["falhas_consecutivas"] == 1
    assert armazenamento.campanha_ativa() is True

    segunda = conector.confirmar(alvo["alvo_id"], "falha", erro="ack 0 de novo")
    assert segunda["pausa_automatica"] is True
    assert armazenamento.campanha_ativa() is False
    assert "pausa automatica" in armazenamento.motivo_pausa()
    assert conector.estado()["liberado"] is False
    with pytest.raises(conector.Bloqueado):
        conector.reservar()


def test_conector_sucesso_zera_falhas_consecutivas(conector_ligado):
    alvo = conector.reservar()
    conector.confirmar(alvo["alvo_id"], "falha", erro="falha isolada")
    assert armazenamento.falhas_consecutivas() == 1

    outro = armazenamento.fila("pendente")[0]
    conector.confirmar(outro["id"], "enviado")
    assert armazenamento.falhas_consecutivas() == 0
    assert armazenamento.campanha_ativa() is True


def test_ativar_zera_falhas_consecutivas(conector_ligado):
    alvo = conector.reservar()
    conector.confirmar(alvo["alvo_id"], "falha", erro="x")
    assert armazenamento.falhas_consecutivas() == 1
    armazenamento.ativar()
    assert armazenamento.falhas_consecutivas() == 0


def test_api_conector_erro_pausa_campanha(conector_ligado):
    resposta = cliente.post(
        "/campanha/conector/erro",
        headers=HEADERS,
        json={"motivo": "desconectado do WhatsApp"},
    )
    assert resposta.status_code == 200
    assert resposta.json()["pausou"] is True
    assert armazenamento.campanha_ativa() is False
    assert "desconectado" in armazenamento.motivo_pausa()
    assert armazenamento.erros_worker() == 1


def test_api_saude_mostra_falhas_e_pausa(conector_ligado):
    alvo = conector.reservar()
    conector.confirmar(alvo["alvo_id"], "falha", erro="ack 0")

    dados = cliente.get("/campanha/saude", headers=HEADERS).json()
    assert dados["status"] == "atencao"
    assert dados["falhas_consecutivas"] == 1
    assert dados["ultimo_erro"] == "ack 0"
    assert dados["falhas_recentes"][0]["erro"] == "ack 0"

    cliente.post(
        "/campanha/conector/erro", headers=HEADERS, json={"motivo": "sessao caiu"}
    )
    dados = cliente.get("/campanha/saude", headers=HEADERS).json()
    assert dados["status"] == "pausada"
    assert dados["ultimo_erro_worker"] == "sessao caiu"


def test_api_parametros_rejeita_max_falhas_fora_da_faixa(conector_ligado):
    resposta = cliente.post(
        "/campanha/parametros", headers=HEADERS, json={"max_falhas_seguidas": 21}
    )
    assert resposta.status_code == 422


def test_api_logs_le_arquivo_do_worker():
    config.LOG_WORKER.unlink(missing_ok=True)
    config.LOG_WORKER.write_text(
        "[10:00:00] linha 1\n[10:00:01] linha 2\n", encoding="utf-8"
    )
    dados = cliente.get("/campanha/logs?linhas=1", headers=HEADERS).json()
    assert dados["existe"] is True
    assert dados["linhas"] == ["[10:00:01] linha 2"]


# --- Envio manual pelo painel (worker --manual) -----------------------------


def test_pedido_manual_ignora_cota_e_intervalo(conector_ligado):
    cliente.post("/campanha/parametros", headers=HEADERS, json={"cota_diaria": 1})
    primeiro = conector.reservar()
    conector.confirmar(primeiro["alvo_id"], "enviado")
    assert conector.estado()["liberado"] is False

    alvo = armazenamento.fila("pendente")[0]
    pedido = armazenamento.criar_pedido(alvo["id"])
    assert pedido is not None

    manual = conector.reservar_manual()
    assert manual["manual"] is True
    assert manual["alvo_id"] == alvo["id"]
    assert manual["pedido_id"] == pedido["id"]
    assert armazenamento.alvo(alvo["id"])["status"] == "enviando"


def test_reservar_manual_sem_pedido_devolve_none(conector_ligado):
    assert conector.reservar_manual() is None


def test_pedido_manual_respeita_optout(conector_ligado):
    alvo = armazenamento.fila("pendente")[0]
    armazenamento.bloquear(alvo["telefone"], motivo="teste")
    armazenamento.criar_pedido(alvo["id"])
    with pytest.raises(conector.Bloqueado):
        conector.reservar_manual()
    assert armazenamento.alvo(alvo["id"])["status"] == "cancelado"


def test_pedido_manual_exige_campanha_ativa(conector_ligado):
    alvo = armazenamento.fila("pendente")[0]
    armazenamento.criar_pedido(alvo["id"])
    armazenamento.pausar("teste")
    with pytest.raises(conector.Bloqueado):
        conector.reservar_manual()


def test_confirmar_fecha_pedido_manual(conector_ligado):
    alvo = armazenamento.fila("pendente")[0]
    armazenamento.criar_pedido(alvo["id"])
    pedido = conector.reservar_manual()
    conector.confirmar(pedido["alvo_id"], "enviado")
    assert armazenamento.pedidos_abertos() == {}


def test_sem_whatsapp_nao_conta_falha_seguida(conector_ligado):
    cliente.post(
        "/campanha/parametros", headers=HEADERS, json={"max_falhas_seguidas": 2}
    )
    for _ in range(3):
        alvo = conector.reservar()
        dados = conector.confirmar(alvo["alvo_id"], "falha", erro="numero sem WhatsApp")
        assert dados["pausa_automatica"] is False
        armazenamento.definir_proximo_envio("")
    assert armazenamento.falhas_consecutivas() == 0
    assert armazenamento.campanha_ativa() is True


def test_api_pedido_exige_worker_manual(conector_ligado):
    alvo = armazenamento.fila("pendente")[0]
    resposta = cliente.post(f"/campanha/fila/{alvo['id']}/enviar", headers=HEADERS)
    assert resposta.status_code == 409
    assert "manual" in resposta.json()["detail"].lower()


def test_api_pulso_e_pedido_manual(conector_ligado):
    alvo = armazenamento.fila("pendente")[0]
    pulso = cliente.post(
        "/campanha/conector/pulso", headers=HEADERS, json={"modo": "manual"}
    )
    assert pulso.status_code == 200
    assert pulso.json()["worker"]["online"] is True

    pedido = cliente.post(f"/campanha/fila/{alvo['id']}/enviar", headers=HEADERS)
    assert pedido.status_code == 200
    assert pedido.json()["pedido"]["alvo_id"] == alvo["id"]

    fila = cliente.get("/campanha/fila", headers=HEADERS).json()
    assert any(item["pedido"] for item in fila["itens"])
    assert fila["worker"]["modo"] == "manual"

    manual = cliente.post(
        "/campanha/conector/manual/proximo", headers=HEADERS
    ).json()
    assert manual["alvo"]["alvo_id"] == alvo["id"]

    vazio = cliente.post(
        "/campanha/conector/manual/proximo", headers=HEADERS
    ).json()
    assert vazio["alvo"] is None


def test_api_cancelar_pedido_manual(conector_ligado):
    alvo = armazenamento.fila("pendente")[0]
    cliente.post(
        "/campanha/conector/pulso", headers=HEADERS, json={"modo": "manual"}
    )
    cliente.post(f"/campanha/fila/{alvo['id']}/enviar", headers=HEADERS)
    resposta = cliente.delete(f"/campanha/fila/{alvo['id']}/enviar", headers=HEADERS)
    assert resposta.json()["cancelado"] is True
    assert armazenamento.pedidos_abertos() == {}


# --- Importar planilha / lista de numeros ------------------------------------

def test_planilha_csv_reconhece_cabecalho():
    conteudo = (
        "Telefone;Nome;Produto;Vencimento\n"
        "(11) 98765-4321;Maria;IPTV;31/12/2026\n"
        "11912345678;Joao;;\n"
    ).encode("utf-8")
    dados = planilha.ler(conteudo, "lista.csv")
    assert dados["total"] == 2
    assert dados["cabecalho"] is True
    assert dados["colunas"]["telefone"] == 1
    linhas = dados["linhas"].splitlines()
    assert linhas[0] == "5511987654321;Maria;IPTV;2026-12-31"
    assert linhas[1] == "5511912345678;Joao"


def test_planilha_xlsx_data_como_data():
    from io import BytesIO

    from openpyxl import Workbook

    pasta = Workbook()
    aba = pasta.active
    aba.append(["telefone", "nome", "produto", "vencimento"])
    aba.append(["11987654321", "Maria", "IPTV", date(2026, 12, 31)])
    buffer = BytesIO()
    pasta.save(buffer)
    dados = planilha.ler(buffer.getvalue(), "clientes.xlsx")
    assert dados["total"] == 1
    assert dados["linhas"].splitlines()[0] == "5511987654321;Maria;IPTV;2026-12-31"


def test_planilha_sem_cabecalho_usa_ordem_das_colunas():
    conteudo = "11987654321;Maria;IPTV;31/12/2026\n".encode("utf-8")
    dados = planilha.ler(conteudo, "sem-cabecalho.csv")
    assert dados["cabecalho"] is False
    assert dados["linhas"].splitlines()[0] == "5511987654321;Maria;IPTV;2026-12-31"


def test_planilha_recusa_formato_e_arquivo_vazio():
    with pytest.raises(planilha.PlanilhaInvalida):
        planilha.ler(b"conteudo", "lista.pdf")
    with pytest.raises(planilha.PlanilhaInvalida):
        planilha.ler(b"", "lista.csv")
    with pytest.raises(planilha.PlanilhaInvalida):
        planilha.ler(b"somente texto\nsem numero\n", "lista.csv")


def test_adicionar_numeros_grava_nome_produto_e_optout(conector_ligado):
    dados = servico.adicionar_numeros(
        "11987654321;Maria;IPTV;31/12/2026\n11912345678",
        modelo="Oi, {nome}! Teste.",
    )
    assert dados["adicionados"] == 2
    itens = {item["telefone"]: item for item in armazenamento.fila("pendente")}
    maria = itens["5511987654321"]
    assert maria["nome"] == "Maria"
    assert maria["produto"] == "IPTV"
    assert maria["vencimento"] == "2026-12-31"
    assert "Maria" in maria["texto"]
    assert "SAIR" in maria["texto"].upper()


def test_adicionar_numeros_descarta_invalidos_e_repetidos(conector_ligado):
    dados = servico.adicionar_numeros(
        "11987654321;Maria\n"
        "11987654321;Maria de novo\n"
        "557581329827;Sem nono digito\n"
        "abc;Sem numero"
    )
    assert dados["adicionados"] == 1
    motivos = {item["motivo"] for item in dados["ignorados"]}
    assert "repetido na lista" in motivos
    assert "12 digitos: confira o 9o digito" in motivos
    assert "telefone invalido" in motivos


def test_adicionar_numeros_respeita_guardas_da_campanha(conector_ligado):
    armazenamento.bloquear("5511900000001", motivo="teste")
    armazenamento.salvar_numero_teste("5511900000002")
    servico.adicionar_numeros("11955554444;Ja na fila")
    linhas = "\n".join(
        ["5511900000001", config.numero_remetente(), "5511900000002", "5511955554444"]
    )
    dados = servico.adicionar_numeros(linhas)
    assert dados["adicionados"] == 0
    motivos = {item["motivo"] for item in dados["ignorados"]}
    assert "pediu para sair (opt-out)" in motivos
    assert "e o proprio remetente" in motivos
    assert "e o numero de teste" in motivos
    assert "ja esta na fila" in motivos


def test_visualizar_numeros_nao_grava(conector_ligado):
    antes = len(armazenamento.fila("pendente"))
    dados = servico.visualizar_numeros("11987654321;Maria")
    assert dados["total_novos"] == 1
    assert dados["novos"][0]["nome"] == "Maria"
    assert len(armazenamento.fila("pendente")) == antes


def test_api_previa_e_gravacao_de_numeros(conector_ligado):
    antes = len(armazenamento.fila("pendente"))
    corpo = {"numeros": "11987654321;Maria;IPTV;31/12/2026", "modelo": "Oi, {nome}!"}
    previa = cliente.post("/campanha/numeros/previa", headers=HEADERS, json=corpo)
    assert previa.status_code == 200
    assert previa.json()["total_novos"] == 1
    assert len(armazenamento.fila("pendente")) == antes

    gravacao = cliente.post("/campanha/numeros", headers=HEADERS, json=corpo)
    assert gravacao.status_code == 200
    assert gravacao.json()["adicionados"] == 1
    assert len(armazenamento.fila("pendente")) == antes + 1


def test_api_planilha_csv_devolve_linhas(conector_ligado):
    arquivos = {
        "arquivo": ("lista.csv", b"telefone;nome\n11987654321;Maria\n", "text/csv")
    }
    resposta = cliente.post("/campanha/planilha", headers=HEADERS, files=arquivos)
    assert resposta.status_code == 200
    dados = resposta.json()
    assert dados["total"] == 1
    assert dados["linhas"].splitlines()[0].startswith("5511987654321")


def test_api_planilha_recusa_formato(conector_ligado):
    arquivos = {"arquivo": ("lista.pdf", b"123", "application/pdf")}
    resposta = cliente.post("/campanha/planilha", headers=HEADERS, files=arquivos)
    assert resposta.status_code == 409


# --- Contatos do WhatsApp ----------------------------------------------------

def test_api_contatos_grava_e_devolve_linhas(conector_ligado):
    itens = [
        {"telefone": "11987654321", "nome": "Maria"},
        {"telefone": "5511912345678", "nome": "João"},
        {"telefone": "123", "nome": "Invalido"},
        {"telefone": config.numero_remetente(), "nome": "Eu mesmo"},
    ]
    resposta = cliente.post("/campanha/contatos", headers=HEADERS, json={"itens": itens})
    assert resposta.status_code == 200
    assert resposta.json()["salvos"] == 2

    dados = cliente.get("/campanha/contatos", headers=HEADERS).json()
    assert dados["total"] == 2
    assert dados["completo_em"]  # ultimo lote marcou a lista como completa
    linhas = dados["linhas"].splitlines()
    assert "5511987654321;Maria" in linhas
    assert any(linha.startswith("5511912345678") for linha in linhas)


def test_api_contatos_parcial_nao_marca_completo(conector_ligado):
    resposta = cliente.post(
        "/campanha/contatos",
        headers=HEADERS,
        json={"itens": [{"telefone": "11987654321", "nome": "Maria"}], "fim": False},
    )
    assert resposta.status_code == 200
    dados = cliente.get("/campanha/contatos", headers=HEADERS).json()
    assert dados["total"] == 1
    assert dados["completo_em"] == ""


def test_api_pedir_contatos_exige_worker_e_consome_uma_vez(conector_ligado):
    assert cliente.post("/campanha/contatos/pedir", headers=HEADERS).status_code == 409

    cliente.post("/campanha/conector/pulso", headers=HEADERS, json={"modo": "manual"})
    pedido = cliente.post("/campanha/contatos/pedir", headers=HEADERS)
    assert pedido.status_code == 200
    assert pedido.json()["pedido_em"]

    primeiro = cliente.post(
        "/campanha/conector/pulso", headers=HEADERS, json={"modo": "manual"}
    ).json()
    assert primeiro["pedir_contatos"] is True

    segundo = cliente.post(
        "/campanha/conector/pulso", headers=HEADERS, json={"modo": "manual"}
    ).json()
    assert segundo["pedir_contatos"] is False


# --- Robo (worker) ligado pelo painel ---------------------------------------

def test_api_worker_status_inicial(conector_ligado):
    dados = cliente.get("/campanha/worker", headers=HEADERS).json()
    assert dados["online"] is False
    assert dados["pid"] == 0
    assert dados["pid_vivo"] is False
    assert dados["script"].endswith("worker.cjs")


def test_api_pulso_guarda_pid_do_worker(conector_ligado):
    cliente.post(
        "/campanha/conector/pulso",
        headers=HEADERS,
        json={"modo": "manual", "pid": 4242},
    )
    assert armazenamento.worker_pid() == 4242
    dados = cliente.get("/campanha/worker", headers=HEADERS).json()
    assert dados["pid"] == 4242


def test_api_worker_ligar_manual(conector_ligado, monkeypatch):
    chamadas = []
    monkeypatch.setattr(
        worker_local,
        "ligar",
        lambda modo="manual": chamadas.append(modo) or {"ligado": True, "modo": modo},
    )
    resposta = cliente.post(
        "/campanha/worker/ligar", headers=HEADERS, json={"modo": "manual"}
    )
    assert resposta.status_code == 200
    assert resposta.json()["ligado"] is True
    assert chamadas == ["manual"]


def test_api_worker_automatico_exige_confirmacao(conector_ligado, monkeypatch):
    monkeypatch.setattr(
        worker_local, "ligar", lambda modo="manual": {"ligado": True, "modo": modo}
    )
    sem_confirmar = cliente.post(
        "/campanha/worker/ligar", headers=HEADERS, json={"modo": "enviar"}
    )
    assert sem_confirmar.status_code == 409

    confirmado = cliente.post(
        "/campanha/worker/ligar",
        headers=HEADERS,
        json={"modo": "enviar", "confirmo": "ENVIAR"},
    )
    assert confirmado.status_code == 200


def test_api_worker_recusa_modo_invalido(conector_ligado):
    resposta = cliente.post(
        "/campanha/worker/ligar", headers=HEADERS, json={"modo": "auto"}
    )
    assert resposta.status_code == 422


def test_api_worker_desligar_sem_robo(conector_ligado):
    dados = cliente.post(
        "/campanha/worker/desligar", headers=HEADERS, json={"forcar": True}
    ).json()
    assert dados["desligado"] is False


def test_api_worker_desligar_pede_parada_uma_vez(conector_ligado):
    cliente.post(
        "/campanha/conector/pulso",
        headers=HEADERS,
        json={"modo": "manual", "pid": 4242},
    )
    dados = cliente.post("/campanha/worker/desligar", headers=HEADERS, json={}).json()
    assert dados["pedido"] is True

    primeiro = cliente.post(
        "/campanha/conector/pulso", headers=HEADERS, json={"modo": "manual", "pid": 4242}
    ).json()
    assert primeiro["parar"] is True

    segundo = cliente.post(
        "/campanha/conector/pulso", headers=HEADERS, json={"modo": "manual", "pid": 4242}
    ).json()
    assert segundo["parar"] is False


def test_api_pulso_guarda_numero_conectado(conector_ligado):
    cliente.post(
        "/campanha/conector/pulso",
        headers=HEADERS,
        json={"modo": "manual", "pid": 4242, "numero": "5511992501859"},
    )
    assert armazenamento.numero_conectado() == "5511992501859"
    dados = cliente.get("/campanha/worker", headers=HEADERS).json()
    assert dados["numero_conectado"] == "5511992501859"


def test_api_conector_numero_normaliza(conector_ligado):
    cliente.post(
        "/campanha/conector/numero",
        headers=HEADERS,
        json={"numero": "(11) 99250-1859"},
    )
    assert armazenamento.numero_conectado() == "5511992501859"

    cliente.post("/campanha/conector/numero", headers=HEADERS, json={"numero": ""})
    assert armazenamento.numero_conectado() == ""


def test_api_worker_desconectar(conector_ligado, monkeypatch):
    monkeypatch.setattr(
        worker_local,
        "desconectar",
        lambda limite=150: {"desconectado": True, "saida": "numero 5511... desconectado"},
    )
    resposta = cliente.post("/campanha/worker/desconectar", headers=HEADERS)
    assert resposta.status_code == 200
    assert resposta.json()["desconectado"] is True


def test_api_worker_desconectar_erro_vira_409(conector_ligado, monkeypatch):
    def falhar(limite=150):
        raise worker_local.WorkerIndisponivel("nao foi possivel desconectar")

    monkeypatch.setattr(worker_local, "desconectar", falhar)
    resposta = cliente.post("/campanha/worker/desconectar", headers=HEADERS)
    assert resposta.status_code == 409
    assert "desconectar" in resposta.json()["detail"]


def test_api_worker_ligar_pareamento(conector_ligado, monkeypatch):
    monkeypatch.setattr(
        worker_local, "ligar", lambda modo="manual": {"ligado": True, "modo": modo}
    )
    resposta = cliente.post(
        "/campanha/worker/ligar", headers=HEADERS, json={"modo": "parear"}
    )
    assert resposta.status_code == 200
    assert resposta.json()["modo"] == "parear"
