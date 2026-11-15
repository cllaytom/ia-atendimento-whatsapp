from __future__ import annotations

from fastapi.testclient import TestClient

from app.atendimento import config as atendimento_config
from app.config import API_KEY
from app.main import app

HEADERS = {"X-API-Key": API_KEY}
client = TestClient(app)


def test_recebe_mensagem_e_responde_pelo_agente():
    dados = client.post(
        "/whatsapp/receber",
        headers=HEADERS,
        json={"contato": "+55 11 90000-0001", "texto": "quanto custa a internet?", "nome": "Teste Ponte"},
    ).json()
    assert dados["estado"] == "ia"
    assert dados["alerta_humano"] is False
    assert dados["respostas"]
    assert "15" in " ".join(dados["respostas"])


def test_pedido_de_humano_traz_alerta_pronto():
    dados = client.post(
        "/whatsapp/receber",
        headers=HEADERS,
        json={"contato": "5511900000002", "texto": "quero falar com um atendente"},
    ).json()
    assert dados["alerta_humano"] is True
    assert dados["alerta_para"] == atendimento_config.ALERTA_WHATSAPP
    assert "Atendimento humano" in dados["alerta_texto"]


def test_continuacao_da_conversa_nao_reinicia():
    client.post(
        "/whatsapp/receber",
        headers=HEADERS,
        json={"contato": "5511900000003", "texto": "quero internet"},
    )
    dados = client.post(
        "/whatsapp/receber",
        headers=HEADERS,
        json={"contato": "5511900000003", "texto": "tim"},
    ).json()
    assert dados["etapa"] == "internet_recarga"


def test_encerrar_conversa():
    client.post(
        "/whatsapp/receber",
        headers=HEADERS,
        json={"contato": "5511900000004", "texto": "oi"},
    )
    resposta = client.post("/whatsapp/encerrar/5511900000004", headers=HEADERS)
    assert resposta.status_code == 200
    assert resposta.json()["encerrada"] is True


def test_exige_chave():
    assert client.post("/whatsapp/receber", json={"contato": "5511900000005", "texto": "oi"}).status_code == 401
