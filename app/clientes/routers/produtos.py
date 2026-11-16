from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import Produto
from ..schemas import ProdutoCreate, ProdutoOut, ProdutoUpdate
from ..security import verificar_api_key
from ..auditoria import registrar

router = APIRouter(prefix='/produtos', tags=['produtos'], dependencies=[Depends(verificar_api_key)])

def _buscar(db, produto_id):
    produto = db.get(Produto, produto_id)
    if produto is None:
        raise HTTPException(404, 'Produto nao encontrado.')
    return produto

def _validar(db, dados, produto_id=None):
    for campo in ('nome', 'dias', 'duracao_fixa', 'ativo'):
        if campo in dados and dados[campo] is None:
            raise HTTPException(422, f'{campo} nao pode ser nulo.')
    if 'nome' in dados:
        dados['nome'] = dados['nome'].strip()
        if not dados['nome']:
            raise HTTPException(422, 'Nome nao pode ser vazio.')
        consulta = select(Produto.id).where(func.upper(func.trim(Produto.nome)) == dados['nome'].upper())
        if produto_id is not None:
            consulta = consulta.where(Produto.id != produto_id)
        if db.scalar(consulta) is not None:
            raise HTTPException(409, 'Produto ja cadastrado.')
    return dados

def _salvar(db):
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, 'Conflito ao salvar produto.')

@router.get('', response_model=list[ProdutoOut])
def listar(db: Session = Depends(get_db)):
    return db.scalars(select(Produto).order_by(Produto.nome)).all()

@router.get('/{produto_id}', response_model=ProdutoOut)
def detalhar(produto_id: int, db: Session = Depends(get_db)):
    return _buscar(db, produto_id)

@router.post('', response_model=ProdutoOut, status_code=201)
def criar(payload: ProdutoCreate, db: Session = Depends(get_db)):
    dados = _validar(db, payload.model_dump())
    produto = Produto(**dados)
    try:
        db.add(produto)
        db.flush()
        registrar(db, 'produto', produto.id, 'criacao', depois=dados)
        _salvar(db)
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, 'Conflito ao criar produto.')
    db.refresh(produto)
    return produto

@router.patch('/{produto_id}', response_model=ProdutoOut)
def atualizar(produto_id: int, payload: ProdutoUpdate, db: Session = Depends(get_db)):
    produto = _buscar(db, produto_id)
    dados = _validar(db, payload.model_dump(exclude_unset=True), produto_id)
    if 'nome' in dados and dados['nome'] != produto.nome:
        raise HTTPException(422, 'Renomeacao bloqueada para preservar vinculos existentes por nome; desative e crie outro produto.')
    antes = {campo: getattr(produto, campo) for campo in dados}
    for campo, valor in dados.items():
        setattr(produto, campo, valor)
    if dados:
        registrar(db, 'produto', produto.id, 'atualizacao', antes=antes, depois=dados)
        _salvar(db)
    db.refresh(produto)
    return produto

@router.delete('/{produto_id}', status_code=204)
def desativar(produto_id: int, db: Session = Depends(get_db)):
    produto = _buscar(db, produto_id)
    antes = {'ativo': produto.ativo}
    produto.ativo = False
    registrar(db, 'produto', produto.id, 'desativacao', antes=antes, depois={'ativo': False})
    _salvar(db)

def semear_produtos(db: Session):
    for nome, fixa in (('IPTV', True), ('INTERNET', False)):
        existente = db.scalar(select(Produto.id).where(func.upper(func.trim(Produto.nome)) == nome))
        if existente is None:
            try:
                with db.begin_nested():
                    db.add(Produto(nome=nome, duracao_fixa=fixa, dias=30, ativo=True))
                    db.flush()
            except IntegrityError:
                if db.scalar(select(Produto.id).where(func.upper(func.trim(Produto.nome)) == nome)) is None:
                    raise
    db.commit()
