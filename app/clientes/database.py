from pathlib import Path
from sqlalchemy import create_engine, event
from sqlalchemy.engine import URL
from sqlalchemy.orm import DeclarativeBase, sessionmaker
BANCO = Path(r'D:\planilhas\dados\assinaturas.db')
if not BANCO.is_file():
    raise RuntimeError('Banco de clientes nao encontrado.')
engine = create_engine(URL.create('sqlite', database=BANCO.as_posix()), connect_args={'check_same_thread': False})
@event.listens_for(engine, 'connect')
def ativar_fk(conexao, registro):
    conexao.execute('PRAGMA foreign_keys=ON')
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
class Base(DeclarativeBase):
    pass
def get_db():
    with SessionLocal() as db:
        yield db
