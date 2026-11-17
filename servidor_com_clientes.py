from fastapi.responses import HTMLResponse, FileResponse
from app.main import app
from app.config import BASE_DIR
from app.clientes.database import Base as ClientesBase, engine as clientes_engine, SessionLocal
from app.clientes import models as clientes_models  # noqa: F401
from app.clientes.routers import assinaturas, planos, relatorios, admin, produtos
from app.clientes.routers.produtos import semear_produtos

modulos = (assinaturas, planos, relatorios, admin, produtos)
for modulo in modulos:
    for rota in modulo.router.routes:
        for existente in app.routes:
            if getattr(existente, 'path', None) == rota.path and (getattr(existente, 'methods', set()) or set()) & (getattr(rota, 'methods', set()) or set()):
                raise RuntimeError(f'Conflito de rota: {rota.path}')
app.router.routes[:] = [r for r in app.router.routes if getattr(r, 'path', None) != '/painel']
for modulo in modulos:
    app.include_router(modulo.router)


@app.on_event('startup')
def preparar_clientes():
    """Cria apenas tabelas ausentes e semeia produtos padrao inexistentes."""
    ClientesBase.metadata.create_all(bind=clientes_engine)
    with SessionLocal() as db:
        semear_produtos(db)


@app.get('/painel', include_in_schema=False)
def painel_clientes():
    html = (BASE_DIR / 'app' / 'clientes' / 'painel.html').read_text(encoding='utf-8')
    html = html.replace('href="http://127.0.0.1:8033/atendimento"', 'href="/atendimento"')
    html = html.replace('</body>', '<script src="/painel-extras.js"></script></body>')
    return HTMLResponse(html, headers={'Cache-Control': 'no-store'})


@app.get('/painel-extras.js', include_in_schema=False)
def painel_extras_script():
    return FileResponse(
        BASE_DIR / 'app' / 'clientes' / 'painel_extras.js',
        media_type='text/javascript',
        headers={'Cache-Control': 'no-store'},
    )


# Filtros do painel de clientes
from app.clientes.filtros import router as filtros_clientes_router
app.include_router(filtros_clientes_router)
