from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import FileResponse, RedirectResponse

from .atendimento import config as atendimento_config
from .atendimento import router as atendimento
from .campanha import router as campanha
from .config import API_KEY, APP_NAME, APP_VERSION, BASE_DIR
from .database import Base, engine
from .routers import admin, assinaturas, planos, relatorios

logger = logging.getLogger("api")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    Base.metadata.create_all(bind=engine)
    if API_KEY == "dev-local-troque-esta-chave":
        logger.warning("API_KEY padrao em uso. Defina a variavel de ambiente API_KEY.")
    if not atendimento_config.LINK_APP_ANDROID:
        logger.warning(
            "LINK_APP_ANDROID nao configurado: o agente pedira que o atendente "
            "envie o link da Play Store."
        )
    if not atendimento_config.ia_ativa():
        logger.info(
            "IA externa desativada. O atendimento funcionara no modo roteirizado."
        )
    yield


app = FastAPI(
    title=APP_NAME,
    version=APP_VERSION,
    lifespan=lifespan,
    description=(
        "API para um agente de IA gerenciar a base de assinaturas: clientes, planos, "
        "vencimentos, renovacoes, pagamentos e despesas.\n\n"
        "Autentique com o header **X-API-Key**."
    ),
)

app.include_router(assinaturas.router)
app.include_router(planos.router)
app.include_router(relatorios.router)
app.include_router(admin.router)
app.include_router(atendimento.router)
app.include_router(campanha.router)


@app.get("/health", tags=["sistema"], summary="Verificacao de saude")
def health():
    return {"status": "ok", "nome": APP_NAME, "versao": APP_VERSION}


@app.get("/", include_in_schema=False)
def raiz():
    return RedirectResponse("/painel")


@app.get("/painel", include_in_schema=False)
def painel():
    return FileResponse(BASE_DIR / "web" / "painel.html")


@app.get("/atendimento", include_in_schema=False)
def atendimento_visual():
    return FileResponse(BASE_DIR / "web" / "atendimento.html")


@app.get("/campanha", include_in_schema=False)
def campanha_visual():
    return FileResponse(BASE_DIR / "web" / "campanha.html")
