from fastapi.responses import HTMLResponse
from app.main import app
from app.config import BASE_DIR
from app.clientes.routers import assinaturas, planos, relatorios, admin

modulos = (assinaturas, planos, relatorios, admin)
for modulo in modulos:
    for rota in modulo.router.routes:
        for existente in app.routes:
            if getattr(existente, 'path', None) == rota.path and (getattr(existente, 'methods', set()) or set()) & (getattr(rota, 'methods', set()) or set()):
                raise RuntimeError(f'Conflito de rota: {rota.path}')
app.router.routes[:] = [r for r in app.router.routes if getattr(r, 'path', None) != '/painel']
for modulo in modulos:
    app.include_router(modulo.router)
@app.get('/painel', include_in_schema=False)
def painel_clientes():
    html = (BASE_DIR / 'app' / 'clientes' / 'painel.html').read_text(encoding='utf-8')
    html = html.replace('href="http://127.0.0.1:8033/atendimento"', 'href="/atendimento"')
    return HTMLResponse(html, headers={'Cache-Control': 'no-store'})

# Filtros do painel de clientes
from app.clientes.filtros import router as filtros_clientes_router
app.include_router(filtros_clientes_router)
