import json
import os
import tempfile
from pathlib import Path

_tmp = tempfile.mkdtemp(prefix="atendimento-teste-")
os.environ.setdefault("DATA_DIR", _tmp)
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_tmp}/teste.db")
os.environ.setdefault("API_KEY", "chave-de-teste")
os.environ["IA_API_KEY"] = ""
os.environ["IA_BASE_URL"] = ""
# Mantem os testes independentes do .env local.
os.environ["LINK_APP_ANDROID"] = ""
os.environ["APP_IPTV_PADRAO"] = ""
os.environ["ATENDIMENTO_PAUSA_ATIVA"] = "0"

from fastapi.testclient import TestClient  # noqa: E402

from app.atendimento import config as atendimento_config  # noqa: E402
from app.atendimento import pausas  # noqa: E402
from app.database import Base, engine  # noqa: E402
from app.main import app  # noqa: E402

Base.metadata.create_all(bind=engine)
cliente = TestClient(app)
HEADERS = {"X-API-Key": "chave-de-teste"}

IMAGEM = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="


def criar(contato):
    resposta = cliente.post(
        "/atendimento/conversas",
        headers=HEADERS,
        json={"contato": contato, "nome": contato},
    )
    assert resposta.status_code == 201, resposta.text
    return resposta.json()


def enviar(conversa_id, texto=None, imagem=None):
    corpo = {}
    if texto is not None:
        corpo["texto"] = texto
    if imagem is not None:
        corpo["imagem"] = imagem
    resposta = cliente.post(
        f"/atendimento/conversas/{conversa_id}/mensagens",
        headers=HEADERS,
        json=corpo,
    )
    assert resposta.status_code == 200, resposta.text
    return resposta.json()


def ultimo_texto(dados):
    return "\n".join(mensagem["texto"] for mensagem in dados["mensagens"])


def test_pagina_e_configuracao_do_atendimento():
    pagina = cliente.get("/atendimento")
    assert pagina.status_code == 200
    assert "Atendimento IA" in pagina.text

    assert cliente.get("/atendimento/conversas").status_code == 401

    config = cliente.get("/atendimento/config", headers=HEADERS)
    assert config.status_code == 200
    assert config.json()["modo"] == "simulador"
    assert "nome_negocio" in config.json()


def test_boas_vindas_e_precos():
    dados = criar("Cliente Preço")
    texto = ultimo_texto(dados)
    assert "Internet ilimitada" in texto
    assert "R$ 15" in texto
    assert "R$ 30" in texto
    assert "R$ 20" in texto
    assert "teste grátis de 4h" in texto.lower()

    dados = enviar(dados["conversa"]["id"], "quanto custa a internet?")
    assert dados["conversa"]["estado"] == "ia"
    assert "R$ 15" in ultimo_texto(dados)


def test_qualificacao_internet_e_transferencia():
    dados = criar("Cliente Internet")
    conversa_id = dados["conversa"]["id"]

    dados = enviar(conversa_id, "1")
    assert dados["conversa"]["etapa"] == "internet_operadora"
    assert "TIM" in ultimo_texto(dados)

    dados = enviar(conversa_id, "Claro")
    assert "apenas com chips" in ultimo_texto(dados)

    dados = enviar(conversa_id, "Vivo")
    assert dados["conversa"]["etapa"] == "internet_recarga"
    assert dados["conversa"]["dados"]["operadora"] == "Vivo"

    dados = enviar(conversa_id, "sim, fiz recarga")
    assert dados["conversa"]["dados"]["recarga"] is True

    if dados["conversa"]["etapa"] == "internet_app":
        dados = enviar(conversa_id, "instalei")
    dados = enviar(conversa_id, "sim")

    assert dados["conversa"]["estado"] == "aguardando_humano"
    assert dados["conversa"]["motivo_transferencia"] == "Contratação — internet"
    assert "Vivo" in dados["conversa"]["resumo"]
    assert "Recarga nos últimos 3 meses: sim" in dados["conversa"]["resumo"]
    assert "Transferido para atendimento humano" in ultimo_texto(dados)

    alertas = cliente.get("/atendimento/alertas", headers=HEADERS).json()
    assert any(item["id"] == conversa_id for item in alertas["itens"])

    dados = cliente.post(
        f"/atendimento/conversas/{conversa_id}/assumir", headers=HEADERS
    ).json()
    assert dados["conversa"]["estado"] == "humano"

    dados = cliente.post(
        f"/atendimento/conversas/{conversa_id}/responder",
        headers=HEADERS,
        json={"texto": "Olá! Vou ativar seu teste agora."},
    ).json()
    assert dados["mensagens"][-1]["autor"] == "humano"

    antes = len(dados["mensagens"])
    dados = enviar(conversa_id, "Qual o link mesmo?")
    assert len(dados["mensagens"]) == antes + 1
    assert dados["mensagens"][-1]["autor"] == "cliente"

    dados = cliente.post(
        f"/atendimento/conversas/{conversa_id}/devolver", headers=HEADERS
    ).json()
    assert dados["conversa"]["estado"] == "ia"
    assert dados["conversa"]["etapa"] == "menu"


def test_explicacao_geral_nao_transfere():
    dados = criar("Cliente Curioso")
    dados = enviar(dados["conversa"]["id"], "como funciona?")

    assert dados["conversa"]["estado"] == "ia"
    texto = ultimo_texto(dados)
    assert "Internet ilimitada" in texto
    assert "IPTV Completo" in texto
    assert "IPTV Básico" in texto
    assert "Qual você quer saber mais?" in texto


def test_explicacao_funciona_mesmo_apos_interesse_de_contratar():
    dados = criar("Cliente Explicação")
    conversa_id = dados["conversa"]["id"]

    dados = enviar(conversa_id, "quero contratar")
    assert "Qual serviço você quer contratar" in ultimo_texto(dados)

    antes = len(dados["mensagens"])
    dados = enviar(conversa_id, "gostaria de saber mais sobre o IPTV")
    texto = "\n".join(
        mensagem["texto"] for mensagem in dados["mensagens"][antes:]
    )
    assert "IPTV" in texto
    assert "R$ 30" in texto
    assert "Qual serviço você quer contratar" not in texto


def test_pausa_de_resposta_variavel_dentro_dos_limites():
    for _ in range(20):
        atraso = pausas.calcular("Olá! Como posso ajudar?")
        assert atendimento_config.PAUSA_MIN <= atraso <= atendimento_config.PAUSA_TETO

    curto = pausas.calcular("oi")
    longo = pausas.calcular("x" * 1000)
    assert longo >= curto or longo == atendimento_config.PAUSA_TETO


def test_saudacao_simples_nao_vira_faq_de_operadora():
    dados = criar("Cliente Oi")
    dados = enviar(dados["conversa"]["id"], "oi")
    ultima = dados["mensagens"][-1]["texto"]
    assert "Como posso te ajudar?" in ultima
    assert "Trabalhamos com chips" not in ultima


def test_faq_de_operadora_quando_cliente_fala_do_chip_oi():
    dados = criar("Cliente Chip Oi")
    dados = enviar(dados["conversa"]["id"], "meu chip é oi, aceita?")
    assert "Trabalhamos com chips" in dados["mensagens"][-1]["texto"]


def test_fluxo_teste_gratis_transfere_com_motivo_correto():
    dados = criar("Cliente Teste")
    conversa_id = dados["conversa"]["id"]

    dados = enviar(conversa_id, "quero o teste grátis")
    assert dados["conversa"]["etapa"] == "internet_operadora"

    dados = enviar(conversa_id, "tim")
    assert dados["conversa"]["etapa"] == "internet_recarga"

    dados = enviar(conversa_id, "sim, recarreguei")
    if dados["conversa"]["etapa"] == "internet_app":
        dados = enviar(conversa_id, "instalei")

    assert dados["conversa"]["estado"] == "aguardando_humano"
    assert dados["conversa"]["motivo_transferencia"] == "Teste grátis de 4h"
    assert dados["conversa"]["dados"]["teste"] is True
    assert "Teste grátis de 4h: sim" in dados["conversa"]["resumo"]


def test_internet_com_link_da_play_store(monkeypatch):
    monkeypatch.setattr(
        atendimento_config,
        "LINK_APP_ANDROID",
        "https://play.google.com/store/apps/details?id=com.linktunnel",
    )
    dados = criar("Cliente Link")
    conversa_id = dados["conversa"]["id"]

    enviar(conversa_id, "1")
    enviar(conversa_id, "vivo")
    dados = enviar(conversa_id, "sim, fiz recarga")

    assert dados["conversa"]["etapa"] == "internet_app"
    assert "play.google.com/store/apps/details?id=com.linktunnel" in ultimo_texto(dados)
    assert "Android" in ultimo_texto(dados)

    dados = enviar(conversa_id, "instalei")
    assert dados["conversa"]["etapa"] == "internet_confirmar"
    assert dados["conversa"]["dados"]["app_instalado"] is True


def test_duvida_sobre_teste_nao_marca_interesse():
    dados = criar("Cliente Dúvida")
    dados = enviar(dados["conversa"]["id"], "quanto custa o teste grátis?")
    assert dados["conversa"]["estado"] == "ia"
    assert dados["conversa"]["dados"].get("teste") is None


def test_fluxo_iptv_com_foto(monkeypatch, tmp_path):
    mapa = tmp_path / "aplicativos.json"
    mapa.write_text(
        json.dumps({"samsung": "SmartOne", "mxq": "XCIPTV"}), encoding="utf-8"
    )
    monkeypatch.setattr(atendimento_config, "ARQUIVO_APLICATIVOS", Path(mapa))

    dados = criar("Cliente IPTV")
    conversa_id = dados["conversa"]["id"]

    dados = enviar(conversa_id, "2")
    assert dados["conversa"]["etapa"] == "iptv_marca"
    assert "marca da sua TV" in ultimo_texto(dados)

    dados = enviar(conversa_id, "Samsung")
    assert dados["conversa"]["etapa"] == "iptv_smart"
    assert dados["conversa"]["dados"]["marca_tv"] == "Samsung"

    dados = enviar(conversa_id, "sim")
    assert dados["conversa"]["etapa"] == "iptv_foto"
    assert "foto da loja de aplicativos" in ultimo_texto(dados)

    dados = enviar(conversa_id, imagem=IMAGEM)
    assert dados["conversa"]["dados"]["foto_loja"] is True
    assert dados["conversa"]["etapa"] == "iptv_tvbox"
    assert dados["mensagens"][-2]["tipo"] == "imagem"

    dados = enviar(conversa_id, "não")
    assert dados["conversa"]["etapa"] == "iptv_confirmar"
    assert "Samsung Smart" in ultimo_texto(dados)
    assert "SmartOne" in ultimo_texto(dados)
    assert dados["conversa"]["dados"]["app_indicado"] == "SmartOne"

    dados = enviar(conversa_id, "sim")
    assert dados["conversa"]["estado"] == "aguardando_humano"
    assert dados["conversa"]["motivo_transferencia"] == "Contratação — IPTV"
    resumo = dados["conversa"]["resumo"]
    assert "IPTV Completo" in resumo
    assert "Marca da TV: Samsung" in resumo
    assert "Foto da loja de aplicativos: sim" in resumo


def test_fluxo_iptv_com_tv_box(monkeypatch, tmp_path):
    mapa = tmp_path / "aplicativos.json"
    mapa.write_text(
        json.dumps({"samsung": "SmartOne", "mxq": "XCIPTV"}), encoding="utf-8"
    )
    monkeypatch.setattr(atendimento_config, "ARQUIVO_APLICATIVOS", Path(mapa))

    dados = criar("Cliente TV Box")
    conversa_id = dados["conversa"]["id"]

    enviar(conversa_id, "3")
    dados = enviar(conversa_id, "Philco")
    assert dados["conversa"]["etapa"] == "iptv_smart"

    dados = enviar(conversa_id, "não")
    assert dados["conversa"]["etapa"] == "iptv_tvbox"

    dados = enviar(conversa_id, "sim")
    assert dados["conversa"]["etapa"] == "iptv_tvbox_modelo"

    dados = enviar(conversa_id, "MXQ")
    assert dados["conversa"]["etapa"] == "iptv_foto"
    assert dados["conversa"]["dados"]["tvbox_modelo"] == "MXQ"

    dados = enviar(conversa_id, "pular")
    assert dados["conversa"]["dados"]["foto_loja"] is False
    assert dados["conversa"]["dados"]["app_indicado"] == "XCIPTV"
    assert "XCIPTV" in ultimo_texto(dados)


def test_pedido_de_atendente_humano():
    dados = criar("Cliente Humano")
    dados = enviar(dados["conversa"]["id"], "quero falar com um atendente")
    assert dados["conversa"]["estado"] == "aguardando_humano"
    assert dados["conversa"]["motivo_transferencia"] == "Cliente pediu atendimento humano"


def test_duvida_fora_do_catalogo_escala_para_humano():
    dados = criar("Cliente Cartão")
    dados = enviar(dados["conversa"]["id"], "vocês aceitam cartão de crédito?")
    assert dados["conversa"]["estado"] == "aguardando_humano"
    assert "fora do catálogo" in dados["conversa"]["motivo_transferencia"]


def _isolar_conhecimento(monkeypatch, tmp_path):
    arquivo = tmp_path / "conhecimento.json"
    monkeypatch.setattr(atendimento_config, "ARQUIVO_CONHECIMENTO", arquivo)
    return arquivo


def _criar_duvida(contato="Cliente Aprendizado"):
    dados = criar(contato)
    conversa_id = dados["conversa"]["id"]
    dados = enviar(conversa_id, "o iptv tem canais de futebol?")
    assert dados["conversa"]["estado"] == "aguardando_humano"

    fila = cliente.get("/atendimento/duvidas", headers=HEADERS).json()
    item = next(
        duvida for duvida in fila["itens"] if duvida["conversa_id"] == conversa_id
    )
    return item


def test_duvida_desconhecida_entra_na_fila_de_aprendizado(monkeypatch, tmp_path):
    _isolar_conhecimento(monkeypatch, tmp_path)
    item = _criar_duvida("Cliente Fila de Dúvidas")

    assert item["status"] == "pendente"
    assert "futebol" in item["pergunta"]
    assert item["contato"] == "Cliente Fila de Dúvidas"


def test_resposta_humana_ensina_o_agente(monkeypatch, tmp_path):
    arquivo = _isolar_conhecimento(monkeypatch, tmp_path)
    item = _criar_duvida("Cliente Ensino")

    resposta = cliente.post(
        f"/atendimento/duvidas/{item['id']}/responder",
        headers=HEADERS,
        json={
            "resposta": "Sim! O IPTV Completo tem canais de futebol.",
            "salvar_na_base": True,
        },
    )
    assert resposta.status_code == 200, resposta.text
    assert resposta.json()["status"] == "respondida"
    assert arquivo.exists()

    base = cliente.get("/atendimento/conhecimento", headers=HEADERS).json()
    assert any("futebol" in entrada["pergunta"] for entrada in base["itens"])

    dados = criar("Cliente Aprendido")
    dados = enviar(dados["conversa"]["id"], "o iptv tem canais de futebol?")
    assert dados["conversa"]["estado"] == "ia"
    assert "canais de futebol" in ultimo_texto(dados)


def test_resposta_humana_sem_salvar_nao_altera_a_base(monkeypatch, tmp_path):
    arquivo = _isolar_conhecimento(monkeypatch, tmp_path)
    item = _criar_duvida("Cliente Sem Salvar")

    resposta = cliente.post(
        f"/atendimento/duvidas/{item['id']}/responder",
        headers=HEADERS,
        json={"resposta": "Ainda vou confirmar com o setor.", "salvar_na_base": False},
    )
    assert resposta.status_code == 200, resposta.text
    assert not arquivo.exists()

    dados = criar("Cliente Sem Resposta")
    dados = enviar(dados["conversa"]["id"], "o iptv tem canais de futebol?")
    assert dados["conversa"]["estado"] == "aguardando_humano"


def test_duvida_ignorada_sai_da_fila(monkeypatch, tmp_path):
    _isolar_conhecimento(monkeypatch, tmp_path)
    item = _criar_duvida("Cliente Ignorado")

    resposta = cliente.post(
        f"/atendimento/duvidas/{item['id']}/ignorar", headers=HEADERS
    )
    assert resposta.status_code == 200, resposta.text
    assert resposta.json()["status"] == "ignorada"

    pendentes = cliente.get(
        "/atendimento/duvidas?status=pendente", headers=HEADERS
    ).json()
    assert all(duvida["id"] != item["id"] for duvida in pendentes["itens"])


def test_adicionar_e_remover_entrada_da_base(monkeypatch, tmp_path):
    _isolar_conhecimento(monkeypatch, tmp_path)

    criada = cliente.post(
        "/atendimento/conhecimento",
        headers=HEADERS,
        json={
            "pergunta": "Vocês parcelam no boleto?",
            "resposta": "Sim, aceitamos boleto e cartão.",
            "termos": ["boleto"],
        },
    )
    assert criada.status_code == 201, criada.text

    base = cliente.get("/atendimento/conhecimento", headers=HEADERS).json()
    entrada = next(
        item for item in base["itens"] if item["pergunta"] == "Vocês parcelam no boleto?"
    )

    dados = criar("Cliente Boleto")
    dados = enviar(dados["conversa"]["id"], "vocês parcelam no boleto?")
    assert dados["conversa"]["estado"] == "ia"
    assert "aceitamos boleto" in ultimo_texto(dados)

    removida = cliente.delete(
        f"/atendimento/conhecimento/{entrada['indice']}", headers=HEADERS
    )
    assert removida.status_code == 200
    sobrando = cliente.get("/atendimento/conhecimento", headers=HEADERS).json()
    assert all(item["pergunta"] != "Vocês parcelam no boleto?" for item in sobrando["itens"])


def test_base_nao_responde_assunto_fora_do_produto(monkeypatch, tmp_path):
    _isolar_conhecimento(monkeypatch, tmp_path)
    cliente.post(
        "/atendimento/conhecimento",
        headers=HEADERS,
        json={
            "pergunta": "Quem ganhou o campeonato?",
            "resposta": "Não falamos sobre isso no atendimento.",
            "termos": ["campeonato"],
        },
    )

    dados = criar("Cliente Fora do Produto")
    dados = enviar(dados["conversa"]["id"], "quem ganhou o campeonato?")
    assert "Não falamos sobre isso" not in ultimo_texto(dados)
    assert dados["conversa"]["estado"] == "aguardando_humano"

