from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.clientes.database import Base, get_db
from app.clientes.models import Produto
from app.clientes.routers.produtos import router, semear_produtos
from app.clientes.security import verificar_api_key


def _app():
    engine = create_engine('sqlite:///:memory:', connect_args={'check_same_thread': False})
    Base.metadata.create_all(bind=engine)
    fabrica = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def banco():
        with fabrica() as sessao:
            yield sessao

    aplicacao = FastAPI()
    aplicacao.include_router(router)
    aplicacao.dependency_overrides[get_db] = banco
    aplicacao.dependency_overrides[verificar_api_key] = lambda: None
    return aplicacao, fabrica


def test_seed_e_idempotente():
    aplicacao, fabrica = _app()
    with fabrica() as db:
        semear_produtos(db)
        semear_produtos(db)
        produtos = db.scalars(select(Produto)).all()
        nomes = {produto.nome.upper() for produto in produtos}
        assert nomes == {'IPTV', 'INTERNET'}
        assert len(produtos) == 2


def test_criar_produto_e_evitar_duplicado():
    aplicacao, _ = _app()
    cliente = TestClient(aplicacao)
    resposta = cliente.post('/produtos', json={
        'nome': 'Teste',
        'duracao_fixa': False,
        'dias': 15,
        'ativo': True,
    })
    assert resposta.status_code == 201
    duplicado = cliente.post('/produtos', json={
        'nome': 'teste',
        'duracao_fixa': False,
        'dias': 15,
    })
    assert duplicado.status_code == 409


def test_atualizar_e_desativar_produto():
    aplicacao, _ = _app()
    cliente = TestClient(aplicacao)
    criado = cliente.post('/produtos', json={
        'nome': 'Teste',
        'duracao_fixa': False,
        'dias': 15,
    }).json()
    atualizado = cliente.patch(f"/produtos/{criado['id']}", json={'dias': 20})
    assert atualizado.status_code == 200
    assert atualizado.json()['dias'] == 20
    desativado = cliente.delete(f"/produtos/{criado['id']}")
    assert desativado.status_code == 204
    detalhe = cliente.get(f"/produtos/{criado['id']}").json()
    assert detalhe['ativo'] is False
