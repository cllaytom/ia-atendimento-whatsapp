from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse

from .atendimento import config as atendimento_config
from .atendimento import router as atendimento
from .atendimento import router_whatsapp, motor, segmentos, suporte_v2
from .config import API_KEY, APP_NAME, APP_VERSION, BASE_DIR
from .database import Base, engine

logger = logging.getLogger("api")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    Base.metadata.create_all(bind=engine)
    suporte_v2.inicializar()
    if API_KEY == "dev-local-troque-esta-chave":
        logger.warning("API_KEY padrao em uso. Defina a variavel de ambiente API_KEY.")
    if not atendimento_config.LINK_APP_ANDROID:
        logger.warning("LINK_APP_ANDROID nao configurado: o agente pedira que o atendente envie o link da Play Store.")
    if not atendimento_config.ia_ativa():
        logger.info("IA externa desativada. O atendimento funcionara no modo roteirizado.")
    yield


app = FastAPI(title=APP_NAME, version=APP_VERSION, lifespan=lifespan, description="Atendimento automatico da ConnectTV. Autentique com o header X-API-Key.")
app.include_router(atendimento.router)
app.include_router(router_whatsapp.router)
app.include_router(segmentos.router)
app.include_router(suporte_v2.router)
# Adaptador compartilhado pelo simulador e pela ponte WhatsApp.
motor.tratar_texto = segmentos.integrar(motor.tratar_texto)


@app.get("/health", tags=["sistema"], summary="Verificacao de saude")
def health():
    return {"status": "ok", "nome": APP_NAME, "versao": APP_VERSION}


@app.get("/", include_in_schema=False)
def raiz():
    return RedirectResponse("/atendimento")


@app.get("/atendimento", include_in_schema=False)
def atendimento_visual():
    pagina = (BASE_DIR / "web" / "atendimento.html").read_text(encoding="utf-8")
    pagina = pagina.replace("</body>", '<script src="/ensino-chat.js?v=1"></script><script src="/segmentos.js?v=1"></script><script src="/revisao-suporte.js?v=1"></script></body>')
    return HTMLResponse(pagina, headers={"Cache-Control": "no-store"})


@app.get("/ensino-chat.js", include_in_schema=False)
def ensino_chat_script():
    return FileResponse(BASE_DIR / "web" / "ensino-chat.js", media_type="text/javascript", headers={"Cache-Control": "no-store"})


@app.get("/segmentos.js", include_in_schema=False)
def segmentos_script():
    return FileResponse(BASE_DIR / "web" / "segmentos.js", media_type="text/javascript", headers={"Cache-Control": "no-store"})


@app.get("/treinamento", include_in_schema=False)
def treinamento_visual():
    return FileResponse(BASE_DIR / "web" / "treinamento.html")


@app.get("/painel", include_in_schema=False)
def painel_antigo():
    return RedirectResponse("/atendimento")


@app.get("/revisao-suporte.js", include_in_schema=False)
def revisao_suporte_script():
    return FileResponse(BASE_DIR / "web" / "revisao-suporte.js", media_type="text/javascript", headers={"Cache-Control": "no-store"})


@app.get("/indicadores", include_in_schema=False)
def indicadores_visual():
    return FileResponse(BASE_DIR / "web" / "indicadores.html", headers={"Cache-Control": "no-store"})
