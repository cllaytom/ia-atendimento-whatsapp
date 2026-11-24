"""Endpoints da campanha (menu Campanha).

Nada aqui dispara mensagem. O POST /campanha/ativar so libera a campanha
quando existir um canal de envio configurado; no modo "previa" ele responde
409 e explica o motivo.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from ..security import verificar_api_key
from . import (
    armazenamento,
    config,
    conector,
    contatos,
    exportacao,
    mensagens,
    midia,
    parametros,
    planilha,
    selecao,
    servico,
    worker_local,
)

router = APIRouter(
    prefix="/campanha",
    tags=["campanha"],
    dependencies=[Depends(verificar_api_key)],
)


class PreviaEntrada(BaseModel):
    modelo: str | None = Field(default=None, max_length=1000)
    produto: str | None = Field(default=None, max_length=60)
    limite: int = Field(default=config.LIMITE_PREVIA, ge=1, le=100)
    variar: bool = True
    apenas_unicos: bool = False


class FilaEntrada(BaseModel):
    modelo: str | None = Field(default=None, max_length=1000)
    produto: str | None = Field(default=None, max_length=60)
    limite: int = Field(default=config.LIMITE_FILA, ge=1, le=500)
    variar: bool = True
    apenas_unicos: bool = False


class NumerosEntrada(BaseModel):
    numeros: str = Field(min_length=1, max_length=200000)
    modelo: str | None = Field(default=None, max_length=2000)
    produto: str | None = Field(default=None, max_length=60)
    vencimento: str | None = Field(default=None, max_length=20)


class ContatoEntrada(BaseModel):
    telefone: str = Field(min_length=1, max_length=40)
    nome: str | None = Field(default=None, max_length=120)


class ContatosEntrada(BaseModel):
    itens: list[ContatoEntrada] = Field(default_factory=list, max_length=5000)
    fim: bool = True


class OptoutEntrada(BaseModel):
    telefone: str = Field(min_length=8, max_length=30)
    motivo: str = Field(default="", max_length=200)


class NumeroEntrada(BaseModel):
    numero: str | None = Field(default=None, max_length=30)
    teste: str | None = Field(default=None, max_length=30)


class PausaEntrada(BaseModel):
    motivo: str = Field(default="", max_length=200)


class AtivarEntrada(BaseModel):
    confirmo: str = Field(default="", max_length=20)


class ConfirmarEntrada(BaseModel):
    alvo_id: int = Field(ge=1)
    situacao: str = Field(pattern="^(enviado|falha|simulado)$")
    erro: str | None = Field(default=None, max_length=300)


class DevolverEntrada(BaseModel):
    alvo_id: int = Field(ge=1)


class ParametrosEntrada(BaseModel):
    cota_diaria: int | None = Field(default=None, ge=0, le=100)
    intervalo_min: int | None = Field(default=None, ge=10, le=3600)
    intervalo_max: int | None = Field(default=None, ge=10, le=3600)
    pausa_cada: int | None = Field(default=None, ge=1, le=100)
    pausa_min: int | None = Field(default=None, ge=30, le=7200)
    pausa_max: int | None = Field(default=None, ge=30, le=7200)
    cooldown_dias: int | None = Field(default=None, ge=0, le=365)
    max_tentativas: int | None = Field(default=None, ge=1, le=5)
    max_falhas_seguidas: int | None = Field(default=None, ge=0, le=20)
    respeitar_janelas: bool | None = None


class ErroWorkerEntrada(BaseModel):
    motivo: str = Field(min_length=1, max_length=300)


class PulsoEntrada(BaseModel):
    modo: str = Field(pattern="^(auto|manual)$")
    pid: int | None = Field(default=None, ge=1, le=4294967295)
    numero: str | None = Field(default=None, max_length=20)


class NumeroConectadoEntrada(BaseModel):
    numero: str = Field(default="", max_length=20)


class WorkerEntrada(BaseModel):
    modo: str = Field(default="manual", pattern="^(manual|enviar|parear)$")
    confirmo: str | None = Field(default=None, max_length=20)
    confirmacao: str | None = Field(default=None, max_length=20)


class WorkerParada(BaseModel):
    forcar: bool = False


@router.get("/worker", summary="Estado do robo (worker) e como ele foi iniciado")
def estado_worker():
    return worker_local.status()


@router.post("/conector/numero", summary="Worker informa o numero pareado")
def conector_numero(entrada: NumeroConectadoEntrada):
    numero = contatos.normalizar(entrada.numero) if entrada.numero.strip() else ""
    armazenamento.salvar_numero_conectado(numero)
    return {"numero": numero}


@router.post(
    "/worker/ligar",
    summary="Sobe o worker em segundo plano (manual = nada sai sozinho)",
)
def ligar_worker(entrada: WorkerEntrada):
    confirmacao = (entrada.confirmo or entrada.confirmacao or "").strip().upper()
    if entrada.modo == "enviar" and confirmacao != "ENVIAR":
        raise HTTPException(
            status_code=409,
            detail=(
                "Modo automatico envia sozinho: confirme digitando ENVIAR. "
                f"Recebido: confirmo={entrada.confirmo!r} | "
                f"confirmacao={entrada.confirmacao!r}"
            ),
        )
    try:
        return worker_local.ligar(entrada.modo)
    except worker_local.WorkerIndisponivel as erro:
        raise HTTPException(status_code=409, detail=str(erro)) from erro


@router.post(
    "/worker/desligar",
    summary="Pede ao worker que encerre (forcar=true mata o processo)",
)
def desligar_worker(entrada: WorkerParada | None = None):
    forcar = bool(entrada and entrada.forcar)
    return worker_local.desligar(forcar=forcar)


@router.post(
    "/worker/desconectar",
    summary="Desvincula o numero atual do WhatsApp (logout de verdade)",
)
def desconectar_worker():
    try:
        return worker_local.desconectar()
    except worker_local.WorkerIndisponivel as erro:
        raise HTTPException(status_code=409, detail=str(erro)) from erro


@router.get("/config", summary="Configuracao visivel da campanha")
def configuracao():
    modo = config.MODO if config.MODO in config.MODOS_VALIDOS else "previa"
    valores = parametros.atuais()
    return {
        "modo": modo,
        "envio_ativo": modo != "previa",
        "ativa": armazenamento.campanha_ativa(),
        "motivo_pausa": armazenamento.motivo_pausa(),
        "marca": config.MARCA,
        "numero_remetente": servico.numero_remetente(),
        "numero_remetente_padrao": config.numero_remetente(),
        "numero_teste": servico.numero_teste(),
        "numero_teste_padrao": config.numero_teste(),
        "worker": armazenamento.worker_status(),
        "rampa": list(config.RAMPA),
        "cap_diario": config.CAP_DIARIO,
        "janelas": [list(janela) for janela in config.JANELAS],
        "dias_semana": list(config.DIAS_SEMANA),
        "cooldown_dias": valores["cooldown_dias"],
        "intervalo": [valores["intervalo_min"], valores["intervalo_max"]],
        "pausa_cada": valores["pausa_cada"],
        "max_falhas_seguidas": valores["max_falhas_seguidas"],
        "parametros": valores,
        "mensagem_padrao": mensagens.PADRAO,
        "variantes": list(mensagens.VARIANTES),
        "base_disponivel": config.BANCO_ASSINATURAS.exists(),
        "banco_campanha": config.BANCO_CAMPANHA.name,
        "metricas": armazenamento.metricas(),
        "aviso": (
            "Modo previa: nada e enviado. A fila e a previa ficam salvas apenas "
            "no banco da campanha."
            if modo == "previa"
            else (
                "Modo arquivo: a fila gera um arquivo para conferencia, sem envio."
                if modo == "arquivo"
                else "Modo real: envio supervisionado pelo conector. A campanha so "
                "envia quando estiver ativada aqui no painel."
            )
        ),
        "envio_real_habilitado": config.ENVIO_REAL_HABILITADO,
        "janelas_ativas": valores["respeitar_janelas"],
        "midia_habilitada": config.MIDIA_HABILITADA,
        "midia_no_primeiro_contato": config.MIDIA_NO_PRIMEIRO_CONTATO,
        "midia_pasta": str(config.MIDIA_PASTA),
        "legenda_flyer": mensagens.legenda_padrao(),
    }


@router.get("/produtos", summary="Produtos existentes na base")
def produtos():
    try:
        return {"itens": selecao.produtos()}
    except selecao.BaseIndisponivel as erro:
        raise HTTPException(status_code=503, detail=str(erro)) from erro


@router.post("/numero", summary="Alterar numero remetente e/ou numero de teste")
def alterar_numero(entrada: NumeroEntrada):
    if not entrada.numero and not entrada.teste:
        raise HTTPException(status_code=422, detail="Informe o numero remetente e/ou o numero de teste.")

    if entrada.numero:
        remetente = contatos.normalizar(entrada.numero)
        if not remetente:
            raise HTTPException(status_code=422, detail="Numero remetente invalido. Informe DDD + numero.")
        armazenamento.salvar_numero_remetente(remetente)

    if entrada.teste:
        teste = contatos.normalizar(entrada.teste)
        if not teste:
            raise HTTPException(status_code=422, detail="Numero de teste invalido. Informe DDD + numero.")
        armazenamento.salvar_numero_teste(teste)

    return {
        "numero_remetente": servico.numero_remetente(),
        "numero_teste": servico.numero_teste(),
        "padrao": {
            "remetente": config.numero_remetente(),
            "teste": config.numero_teste(),
        },
    }


@router.get("/parametros", summary="Parametros de envio ajustaveis no painel")
def ler_parametros():
    return {
        "parametros": parametros.atuais(),
        "padroes": parametros.padroes(),
        "limites": parametros.limites(),
        "salvos": parametros.salvos(),
    }


@router.post("/parametros", summary="Salvar parametros de envio")
def gravar_parametros(entrada: ParametrosEntrada):
    dados = entrada.model_dump(exclude_none=True)
    try:
        valores = parametros.salvar(dados)
    except ValueError as erro:
        raise HTTPException(status_code=422, detail=str(erro)) from erro
    return {"parametros": valores, "estado": conector.estado()}


@router.delete("/parametros", summary="Restaurar parametros de envio padrao")
def restaurar_parametros():
    return {"parametros": parametros.restaurar(), "estado": conector.estado()}


@router.post("/exportar", summary="Gerar arquivo do lote pendente (sem envio)")
def exportar(limite: int = Query(default=50, ge=1, le=500)):
    itens = armazenamento.fila("pendente")[:limite]
    if not itens:
        raise HTTPException(status_code=409, detail="Fila vazia. Monte a fila antes de exportar.")
    dados = exportacao.exportar_lote(itens)
    return {**dados, "metricas": armazenamento.metricas()}


@router.get("/midias", summary="Imagens aprovadas para a fase 2 (somente leitura)")
def midias():
    dados = midia.listar()
    dados["legenda"] = midia.legenda()
    return dados


@router.get("/midias/legenda", summary="Legenda do flyer, com opt-out garantido")
def legenda_flyer(extra: str = Query(default="", max_length=300)):
    return midia.legenda(extra=extra)


@router.get("/midias/{nome}", summary="Abrir uma imagem da pasta aprovada")
def ver_midia(nome: str):
    caminho = midia.resolver(nome)
    if not caminho:
        raise HTTPException(status_code=404, detail="Imagem nao encontrada na pasta aprovada.")
    return FileResponse(caminho, headers={"Cache-Control": "no-store"})


@router.get("/elegiveis", summary="Clientes que podem entrar na campanha")
def elegiveis(
    produto: str | None = Query(default=None, max_length=60),
    limite: int = Query(default=config.LIMITE_PREVIA, ge=1, le=500),
    apenas_unicos: bool = Query(default=False),
):
    dados = servico.elegiveis(produto=produto, limite=limite, apenas_unicos=apenas_unicos)
    if not dados["disponivel"]:
        raise HTTPException(status_code=503, detail=dados["erro"])
    return dados


@router.get("/compartilhados", summary="Numeros usados por mais de um cadastro")
def compartilhados(minimo: int = Query(default=2, ge=2, le=20)):
    try:
        itens = servico.compartilhados(minimo=minimo)
    except selecao.BaseIndisponivel as erro:
        raise HTTPException(status_code=503, detail=str(erro)) from erro
    return {
        "itens": itens,
        "total_numeros": len(itens),
        "total_clientes": sum(item["total"] for item in itens),
    }


@router.post("/previa", summary="Mostrar as mensagens sem gravar nada")
def previa(entrada: PreviaEntrada):
    dados = servico.previa(
        modelo=entrada.modelo,
        produto=entrada.produto,
        limite=entrada.limite,
        variar=entrada.variar,
        apenas_unicos=entrada.apenas_unicos,
    )
    if not dados["disponivel"]:
        raise HTTPException(status_code=503, detail=dados["erro"])
    return dados


@router.post("/fila", summary="Gravar os alvos escolhidos no banco da campanha", status_code=201)
def criar_fila(entrada: FilaEntrada):
    dados = servico.criar_fila(
        modelo=entrada.modelo,
        produto=entrada.produto,
        limite=entrada.limite,
        variar=entrada.variar,
        apenas_unicos=entrada.apenas_unicos,
    )
    if not dados["disponivel"]:
        raise HTTPException(status_code=503, detail=dados["erro"])
    return {
        "criados": dados["criados"],
        "considerados": dados["total"],
        "resumo": dados["resumo"],
        "metricas": armazenamento.metricas(),
    }


@router.post(
    "/planilha",
    summary="Ler .xlsx/.xlsb/.csv e devolver as linhas para conferencia (sem gravar)",
)
async def ler_planilha(arquivo: UploadFile = File(...)):
    conteudo = await arquivo.read()
    if len(conteudo) > 8 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Planilha maior que 8 MB.")
    try:
        dados = planilha.ler(conteudo, arquivo.filename or "")
    except planilha.PlanilhaInvalida as erro:
        raise HTTPException(status_code=409, detail=str(erro)) from erro
    return dados


@router.post("/numeros/previa", summary="Conferir a lista de numeros sem gravar nada")
def previa_numeros(entrada: NumerosEntrada):
    dados = servico.visualizar_numeros(
        entrada.numeros,
        modelo=entrada.modelo,
        produto=entrada.produto,
        vencimento=entrada.vencimento,
    )
    return dados


@router.post("/numeros", summary="Gravar a lista de numeros na fila (sem enviar)")
def adicionar_numeros(entrada: NumerosEntrada):
    dados = servico.adicionar_numeros(
        entrada.numeros,
        modelo=entrada.modelo,
        produto=entrada.produto,
        vencimento=entrada.vencimento,
    )
    return {**dados, "metricas": armazenamento.metricas()}


@router.post("/contatos", summary="Worker envia a lista de contatos do WhatsApp")
def receber_contatos(entrada: ContatosEntrada):
    proibidos = {servico.numero_remetente(), servico.numero_teste()}
    prontos = []
    for item in entrada.itens:
        telefone = contatos.normalizar(item.telefone)
        if not telefone or len(telefone) != 13 or telefone in proibidos:
            continue
        prontos.append({"telefone": telefone, "nome": (item.nome or "").strip()})
    salvos = armazenamento.salvar_contatos_whatsapp(prontos)
    if entrada.fim:
        armazenamento.marcar_contatos_completos()
    return {"recebidos": len(entrada.itens), "salvos": salvos, "fim": entrada.fim}


@router.get("/contatos", summary="Lista de contatos recebida do WhatsApp")
def listar_contatos():
    itens = armazenamento.contatos_whatsapp()
    linhas = []
    for item in itens:
        nome = (item.get("nome") or "").strip()
        linhas.append(f"{item['telefone']};{nome}" if nome else item["telefone"])
    resumo = armazenamento.resumo_contatos_whatsapp()
    return {
        "total": resumo["total"],
        "atualizado_em": resumo["atualizado_em"],
        "completo_em": armazenamento.contatos_completos_em(),
        "linhas": "\n".join(linhas),
        "itens": itens[:50],
    }


@router.post(
    "/contatos/pedir", summary="Pedir ao worker conectado a lista de contatos"
)
def pedir_contatos():
    trabalho = armazenamento.worker_status()
    if not trabalho["online"]:
        raise HTTPException(
            status_code=409,
            detail=(
                "Nenhum worker online. Abra o worker "
                "(campanha-whatsapp\\start.cmd --manual) e tente de novo."
            ),
        )
    momento = armazenamento.pedir_contatos()
    return {"pedido": True, "pedido_em": momento}


@router.get("/fila", summary="Fila da campanha")
def listar_fila(
    status: str | None = Query(default=None, max_length=20),
    limite: int = Query(default=200, ge=1, le=1000),
):
    abertos = armazenamento.pedidos_abertos()
    itens = []
    for item in armazenamento.fila(status)[:limite]:
        item = dict(item)
        pedido = abertos.get(item["id"])
        item["pedido"] = pedido["id"] if pedido else None
        itens.append(item)
    return {
        "itens": itens,
        "metricas": armazenamento.metricas(),
        "worker": armazenamento.worker_status(),
    }


@router.delete("/fila", summary="Remover da fila os alvos ainda pendentes")
def limpar_fila():
    removidos = armazenamento.limpar_pendentes()
    return {"removidos": removidos, "metricas": armazenamento.metricas()}


@router.delete("/fila/{alvo_id}", summary="Remover um alvo pendente da fila")
def remover_alvo(alvo_id: int):
    if not armazenamento.remover_alvo(alvo_id):
        raise HTTPException(status_code=404, detail="Alvo pendente nao encontrado.")
    return {"removido": alvo_id, "metricas": armazenamento.metricas()}


@router.post(
    "/fila/{alvo_id}/enviar",
    summary="Pedir envio manual deste alvo (worker em modo manual)",
)
def pedir_envio(alvo_id: int):
    trabalho = armazenamento.worker_status()
    if not trabalho["online"] or trabalho["modo"] != "manual":
        raise HTTPException(
            status_code=409,
            detail=(
                "Nenhum worker em modo manual conectado. "
                "Abra outra janela com: campanha-whatsapp\\start.cmd --manual"
            ),
        )
    if not armazenamento.campanha_ativa():
        raise HTTPException(
            status_code=409, detail="Campanha desligada. Ative antes de enviar."
        )
    pedido = armazenamento.criar_pedido(alvo_id)
    if not pedido:
        raise HTTPException(status_code=404, detail="Alvo pendente nao encontrado.")
    return {"pedido": pedido, "alvo_id": alvo_id}


@router.delete(
    "/fila/{alvo_id}/enviar", summary="Cancelar o pedido de envio manual"
)
def cancelar_envio(alvo_id: int):
    return {"cancelado": armazenamento.cancelar_pedido(alvo_id)}


@router.get("/plano", summary="Distribuicao da fila por dia util (rampa)")
def plano():
    return servico.plano()


@router.get("/optouts", summary="Numeros que nao devem receber campanha")
def listar_optouts():
    itens = list(armazenamento.optouts().values())
    return {"itens": itens, "total": len(itens)}


@router.post("/optouts", summary="Bloquear um numero (recusa global)", status_code=201)
def criar_optout(entrada: OptoutEntrada):
    telefone = contatos.normalizar(entrada.telefone)
    if not telefone:
        raise HTTPException(status_code=422, detail="Telefone invalido. Informe DDD + numero.")
    armazenamento.bloquear(telefone, motivo=entrada.motivo, origem="manual")
    removidos = armazenamento.remover_pendentes_do_telefone(telefone)
    return {"telefone": telefone, "removidos_da_fila": removidos}


@router.delete("/optouts/{telefone}", summary="Desbloquear um numero")
def remover_optout(telefone: str):
    numero = contatos.normalizar(telefone)
    if not numero:
        raise HTTPException(status_code=422, detail="Telefone invalido.")
    if not armazenamento.desbloquear(numero):
        raise HTTPException(status_code=404, detail="Numero nao estava bloqueado.")
    return {"telefone": numero, "bloqueado": False}


@router.post("/ativar", summary="Ligar a campanha (manual)")
def ativar(entrada: AtivarEntrada | None = None):
    if not config.ENVIO_REAL_HABILITADO:
        raise HTTPException(
            status_code=409,
            detail=(
                "Envio real desativado por trava de seguranca. Nada sera enviado sem "
                "liberacao explicita (fase 2 supervisionada)."
            ),
        )
    modo = config.MODO if config.MODO in config.MODOS_VALIDOS else "previa"
    if modo != config.MODO_REAL:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Modo {modo}: nenhum canal de envio habilitado. A fila pode ser "
                "montada e revisada, mas nada sera enviado. O envio real exige "
                "CAMPANHA_MODO=real e o conector aberto."
            ),
        )
    if (entrada.confirmo if entrada else "").strip().upper() != "ENVIAR":
        raise HTTPException(
            status_code=422,
            detail='Para ligar a campanha no modo real, envie {"confirmo": "ENVIAR"}.',
        )
    if not armazenamento.fila("pendente"):
        raise HTTPException(status_code=409, detail="Fila vazia. Monte a fila antes de ativar.")
    armazenamento.ativar()
    return {"ativa": True, "modo": modo}


@router.post("/pausar", summary="Desligar a campanha (manual)")
def pausar(entrada: PausaEntrada | None = None):
    armazenamento.pausar(entrada.motivo if entrada else "")
    return {"ativa": False, "motivo": armazenamento.motivo_pausa()}


@router.get("/envios", summary="Historico de envios da campanha")
def listar_envios(limite: int = Query(default=100, ge=1, le=1000)):
    return {"itens": armazenamento.envios(limite), "metricas": armazenamento.metricas()}


@router.get("/saude", summary="Saude do envio (falhas, pausa e ultimos erros)")
def saude():
    valores = parametros.atuais()
    seguidas = armazenamento.falhas_consecutivas()
    limite = valores["max_falhas_seguidas"]
    ativa = armazenamento.campanha_ativa()
    if not ativa:
        status = "pausada" if armazenamento.motivo_pausa() else "desligada"
    elif limite > 0 and seguidas > 0:
        status = "atencao"
    else:
        status = "ok"

    falhas_recentes = [
        item for item in armazenamento.envios(200) if item["situacao"] == "falha"
    ][:5]
    return {
        "status": status,
        "ativa": ativa,
        "motivo_pausa": armazenamento.motivo_pausa(),
        "worker": armazenamento.worker_status(),
        "falhas_consecutivas": seguidas,
        "limite_falhas": limite,
        "ultimo_erro": armazenamento.ultimo_erro(),
        "ultimo_erro_em": armazenamento.ultimo_erro_em(),
        "erros_worker": armazenamento.erros_worker(),
        "ultimo_erro_worker": armazenamento.ultimo_erro_worker(),
        "ultimo_erro_worker_em": armazenamento.ultimo_erro_worker_em(),
        "falhas_recentes": falhas_recentes,
    }


@router.get("/logs", summary="Ultimas linhas do log do worker")
def logs(linhas: int = Query(default=40, ge=1, le=500)):
    caminho = config.LOG_WORKER
    if not caminho.exists():
        return {"arquivo": caminho.name, "existe": False, "linhas": []}
    try:
        with caminho.open("r", encoding="utf-8", errors="replace") as arquivo:
            conteudo = arquivo.readlines()
    except OSError as erro:
        raise HTTPException(
            status_code=503, detail=f"Nao foi possivel ler o log do worker: {erro}"
        ) from erro
    return {
        "arquivo": caminho.name,
        "existe": True,
        "linhas": [linha.rstrip("\n") for linha in conteudo[-linhas:]],
    }


# ------------------------- conector (fase 2) -------------------------------
# O worker Node so obedece: pergunta o estado, reserva 1 alvo e confirma o
# resultado. Toda a decisao (trava, janela, cota, ritmo) fica no Python.


def _bloqueado(erro: conector.Bloqueado) -> HTTPException:
    return HTTPException(
        status_code=409,
        detail={"motivo": erro.motivo, "esperar_segundos": erro.esperar},
    )


@router.get("/conector/estado", summary="O que o conector pode fazer agora")
def conector_estado():
    return conector.estado()


@router.post("/conector/proximo", summary="Reservar o proximo alvo (1 por vez)")
def conector_proximo():
    try:
        return conector.reservar()
    except conector.Bloqueado as erro:
        raise _bloqueado(erro) from erro


@router.post("/conector/confirmar", summary="Registrar o resultado de um envio")
def conector_confirmar(entrada: ConfirmarEntrada):
    try:
        return conector.confirmar(
            alvo_id=entrada.alvo_id,
            situacao=entrada.situacao,
            erro=entrada.erro,
        )
    except conector.Bloqueado as erro:
        raise _bloqueado(erro) from erro


@router.post("/conector/devolver", summary="Desfazer uma reserva sem gravar envio")
def conector_devolver(entrada: DevolverEntrada):
    try:
        return conector.devolver(entrada.alvo_id)
    except conector.Bloqueado as erro:
        raise _bloqueado(erro) from erro


@router.post(
    "/conector/manual/proximo",
    summary="Reservar o proximo envio pedido no painel (modo manual)",
)
def conector_manual():
    try:
        alvo = conector.reservar_manual()
    except conector.Bloqueado as erro:
        raise _bloqueado(erro) from erro
    return {"alvo": alvo}


@router.post("/conector/pulso", summary="Worker informa que esta online e o modo")
def conector_pulso(entrada: PulsoEntrada):
    armazenamento.registrar_worker(entrada.modo, entrada.pid)
    if entrada.numero is not None:
        numero = contatos.normalizar(entrada.numero) if entrada.numero.strip() else ""
        armazenamento.salvar_numero_conectado(numero)
    return {
        "ok": True,
        "worker": armazenamento.worker_status(),
        "pedir_contatos": armazenamento.consumir_pedido_contatos(),
        "parar": armazenamento.consumir_pedido_parada(),
    }


@router.post("/conector/erro", summary="Registrar erro fatal do worker e pausar a campanha")
def conector_erro(entrada: ErroWorkerEntrada):
    total = armazenamento.registrar_erro_worker(entrada.motivo)
    armazenamento.pausar(f"pausa automatica: {entrada.motivo}"[:200])
    return {
        "pausou": True,
        "motivo": armazenamento.motivo_pausa(),
        "erros_worker": total,
        "estado": conector.estado(),
    }
