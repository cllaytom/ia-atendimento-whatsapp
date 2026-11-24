from __future__ import annotations

from . import config
from .texto import extrair_plano_iptv, tem

# ---------------------------------------------------------------------------
# Precos oficiais. O agente nao pode inventar outros valores.
# ---------------------------------------------------------------------------
INTERNET_PRIMEIRO = 15.0
INTERNET_DEPOIS = 20.0
INTERNET_TRIAL_HORAS = 4

IPTV_COMPLETO_PRIMEIRO = 30.0
IPTV_COMPLETO_DEPOIS = 35.0
IPTV_BASICO_PRIMEIRO = 20.0
IPTV_BASICO_DEPOIS = 30.0

PRECOS_VALIDOS = {
    INTERNET_PRIMEIRO,
    INTERNET_DEPOIS,
    IPTV_COMPLETO_PRIMEIRO,
    IPTV_COMPLETO_DEPOIS,
    IPTV_BASICO_PRIMEIRO,
    IPTV_BASICO_DEPOIS,
}


def brl(valor: float) -> str:
    return f"R$ {valor:,.0f}".replace(",", ".")


def nome_plano(codigo: str | None) -> str:
    return {
        "internet": "Internet ilimitada + VPN",
        "completo": "IPTV Completo",
        "basico": "IPTV Básico",
    }.get(codigo or "", "serviço")


def valores_plano(codigo: str | None) -> tuple[float, float] | None:
    return {
        "internet": (INTERNET_PRIMEIRO, INTERNET_DEPOIS),
        "completo": (IPTV_COMPLETO_PRIMEIRO, IPTV_COMPLETO_DEPOIS),
        "basico": (IPTV_BASICO_PRIMEIRO, IPTV_BASICO_DEPOIS),
    }.get(codigo or "")


def resumo_valores(codigo: str | None) -> str:
    valores = valores_plano(codigo)
    if not valores:
        return ""
    primeiro, depois = valores
    return f"{brl(primeiro)} no 1º mês (depois {brl(depois)})"


# ---------------------------------------------------------------------------
# Mensagens do agente
# ---------------------------------------------------------------------------
def boas_vindas() -> str:
    return (
        f"Olá! 👋 Eu sou o assistente virtual da *{config.NOME_NEGOCIO}*.\n\n"
        "Posso te ajudar com:\n\n"
        f"1️⃣ *Internet ilimitada + VPN* — {brl(INTERNET_PRIMEIRO)} no 1º mês "
        f"(depois {brl(INTERNET_DEPOIS)}), com teste grátis de {INTERNET_TRIAL_HORAS}h. "
        "Somente Android.\n"
        f"2️⃣ *IPTV Completo* — todos os streamers — {brl(IPTV_COMPLETO_PRIMEIRO)} no 1º mês "
        f"(depois {brl(IPTV_COMPLETO_DEPOIS)}).\n"
        f"3️⃣ *IPTV Básico* — {brl(IPTV_BASICO_PRIMEIRO)} no 1º mês "
        f"(depois {brl(IPTV_BASICO_DEPOIS)}).\n"
        "4️⃣ *Falar com um atendente*\n\n"
        "Digite o número da opção ou me conte o que você precisa. 😊"
    )


def menu_curto() -> str:
    return (
        "Como posso te ajudar?\n\n"
        "*1* Internet ilimitada + VPN (somente Android)\n"
        "*2* IPTV Completo\n"
        "*3* IPTV Básico\n"
        "*4* Falar com um atendente"
    )


MSG_TRANSFERENCIA = (
    "Perfeito! ✅ Vou te passar para um atendente humano agora. "
    "Só um instante, por favor. 🙋"
)

MSG_TRANSFERENCIA_PEDIDO = (
    "Claro! Vou chamar um atendente humano para você agora. "
    "Só um instante, por favor. 🙋"
)


def inicio_internet() -> str:
    return (
        "Ótima escolha! 🚀 A internet ilimitada + VPN funciona apenas em *Android* — "
        "não temos opção para iPhone.\n\n"
        "Para começar: seu chip é da *TIM* ou da *Vivo*?"
    )


def pergunta_recarga() -> str:
    return (
        "Perfeito! Agora me confirma: você fez alguma *recarga nos últimos 3 meses*? "
        "Isso é necessário para o chip estar ativo. (sim/não)"
    )


def internet_qualificada(encaminhando: bool = False) -> str:
    if config.LINK_APP_ANDROID:
        return (
            "Tudo certo! ✅ Seu chip atende aos requisitos.\n\n"
            "Baixe nosso aplicativo na Play Store (somente Android):\n"
            f"{config.LINK_APP_ANDROID}\n\n"
            "Depois de instalar, me avise por aqui que eu te passo para o atendente "
            f"ativar seu *teste grátis de {INTERNET_TRIAL_HORAS}h* ou seu plano de "
            f"{brl(INTERNET_PRIMEIRO)} no 1º mês."
        )
    if encaminhando:
        return (
            "Tudo certo! ✅ Seu chip atende aos requisitos.\n\n"
            "O atendente vai te enviar o link do aplicativo da Play Store e ativar seu "
            f"*teste grátis de {INTERNET_TRIAL_HORAS}h* ou seu plano de "
            f"{brl(INTERNET_PRIMEIRO)} no 1º mês. Vou te passar para ele agora."
        )
    return (
        "Tudo certo! ✅ Seu chip atende aos requisitos.\n\n"
        "O atendente vai te enviar o link do aplicativo da Play Store e ativar seu "
        f"*teste grátis de {INTERNET_TRIAL_HORAS}h* ou seu plano de "
        f"{brl(INTERNET_PRIMEIRO)} no 1º mês.\n\n"
        "Quer que eu já te passe para ele? (sim/não)"
    )


def internet_sem_recarga() -> str:
    return (
        "Sem uma recarga nos últimos 3 meses, o chip pode estar inativo e não conseguimos "
        "ativar o serviço. 😕\n\n"
        "Faça uma recarga e me avise por aqui — ou digite *atendente* que eu te passo "
        "para alguém da equipe."
    )


def internet_operadora_invalida() -> str:
    return (
        "Atualmente a internet ilimitada + VPN funciona apenas com chips *TIM* ou *Vivo*. "
        "Se você tiver um chip de uma dessas operadoras, me avisa que eu continuo. "
        "Se preferir, digite *atendente*."
    )


def sem_iphone() -> str:
    return (
        "Infelizmente o serviço é somente para *Android* — não temos opção para iPhone. 📵\n\n"
        "Se você tiver um celular Android, me avisa que eu continuo o atendimento."
    )


def pergunta_instalou() -> str:
    return "Instalou o aplicativo? Me avise que já te passo para o atendente ativar. 😊"


def confirmar_internet() -> str:
    return (
        "Quer ativar agora seu *teste grátis de 4h* ou o plano de "
        f"*{brl(INTERNET_PRIMEIRO)} no 1º mês* (depois {brl(INTERNET_DEPOIS)})? (sim/não)"
    )


def planos_iptv() -> str:
    return (
        "Temos dois planos de IPTV:\n\n"
        f"2️⃣ *Completo* — todos os streamers — {brl(IPTV_COMPLETO_PRIMEIRO)} no 1º mês "
        f"(depois {brl(IPTV_COMPLETO_DEPOIS)})\n"
        f"3️⃣ *Básico* — {brl(IPTV_BASICO_PRIMEIRO)} no 1º mês "
        f"(depois {brl(IPTV_BASICO_DEPOIS)})\n\n"
        "Qual você quer? (2 ou 3)"
    )


def pergunta_marca() -> str:
    return (
        "Perfeito! Para eu indicar o aplicativo certo: qual é a *marca da sua TV*? "
        "(ex.: Samsung, LG, TCL, Philco...)"
    )


def pergunta_smart() -> str:
    return "Sua TV é *Smart*? (sim/não)"


def pergunta_foto_tv() -> str:
    return (
        "Legal! Agora me envia uma *foto da loja de aplicativos* da sua TV. 📷\n\n"
        "No controle, abra a loja de apps (Play Store, Samsung Apps, LG Content Store...) "
        "e tire uma foto da tela. Se não conseguir, digite *pular*."
    )


def pergunta_tvbox() -> str:
    return (
        "Você usa *TV Box*? Se sim, me informe o *modelo* dele. "
        "Se não, responda *não*."
    )


def pergunta_modelo_tvbox() -> str:
    return (
        "Qual é o *modelo do seu TV Box*? "
        "(ex.: MXQ, TX3 Mini, Fire TV Stick...)"
    )


def pergunta_foto_tvbox() -> str:
    return (
        "Agora me envia uma *foto da loja de aplicativos* do seu TV Box. 📷 "
        "Se não conseguir, digite *pular*."
    )


def sem_smart_tv_sem_box() -> str:
    return (
        "Para usar o IPTV você precisa de uma *Smart TV* ou de um *TV Box* compatível. "
        "Se você tiver outro aparelho, me conta qual é. Se preferir, digite *atendente* "
        "que eu te ajudo."
    )


def iptv_qualificado(
    dispositivo: str, aplicativo: str | None, perguntar: bool = True
) -> str:
    if aplicativo:
        indicacao = (
            f"Para o seu *{dispositivo}*, o aplicativo indicado é o *{aplicativo}*."
        )
    else:
        indicacao = (
            f"Anotei seu aparelho (*{dispositivo}*). Vou confirmar com o atendente "
            "qual é o aplicativo correto para ele."
        )
    if not perguntar:
        return (
            f"Perfeito, já tenho tudo que preciso! ✅\n\n{indicacao}\n\n"
            "Vou te passar para o atendente para finalizar."
        )
    return (
        f"Perfeito, já tenho tudo que preciso! ✅\n\n{indicacao}\n\n"
        "Quer ativar agora? (sim/não)"
    )


# ---------------------------------------------------------------------------
# Perguntas frequentes (funcionam mesmo sem IA configurada)
# ---------------------------------------------------------------------------
def faq_internet() -> str:
    return (
        f"A internet ilimitada + VPN está em promoção: *{brl(INTERNET_PRIMEIRO)} no 1º mês* "
        f"e *{brl(INTERNET_DEPOIS)}* a partir do 2º mês. Inclui *teste grátis de "
        f"{INTERNET_TRIAL_HORAS}h*.\n\n"
        "Funciona somente em *Android*, com chip *TIM* ou *Vivo* e recarga nos últimos "
        "3 meses."
    )


def faq_iptv() -> str:
    return (
        f"O IPTV *Completo* (todos os streamers) está {brl(IPTV_COMPLETO_PRIMEIRO)} no "
        f"1º mês e {brl(IPTV_COMPLETO_DEPOIS)} depois.\n"
        f"O *Básico* está {brl(IPTV_BASICO_PRIMEIRO)} no 1º mês e "
        f"{brl(IPTV_BASICO_DEPOIS)} depois."
    )


def faq_teste() -> str:
    return (
        f"O teste grátis é de *{INTERNET_TRIAL_HORAS} horas*, para a internet ilimitada "
        "+ VPN.\n\n"
        "Para liberar, preciso confirmar se seu chip é *TIM* ou *Vivo* e se você fez "
        "recarga nos últimos 3 meses. O serviço é somente para *Android*."
    )


def faq_operadoras() -> str:
    return (
        "Trabalhamos com chips *TIM* e *Vivo*. O chip precisa ter recebido uma recarga "
        "nos últimos 3 meses para estar ativo."
    )


def faq_recarga() -> str:
    return (
        "A recarga nos últimos 3 meses é necessária para manter o chip ativo. "
        "Sem ela, o chip pode estar inativo e a ativação não funciona."
    )


def faq_aplicativo() -> str:
    texto = (
        "O aplicativo é instalado pela *Play Store*, somente em celular *Android*. "
        "Não temos opção para iPhone."
    )
    if config.LINK_APP_ANDROID:
        texto += f"\n\nLink: {config.LINK_APP_ANDROID}"
    return texto


def faq_streamers() -> str:
    return (
        "O plano *Completo* inclui todos os streamers. O *Básico* é o plano de entrada, "
        "com valor menor."
    )


def faq_vpn() -> str:
    return (
        "A VPN protege sua conexão e ajuda a manter sua privacidade enquanto você usa "
        "a internet. O plano já inclui a VPN."
    )


def explicacao_geral() -> str:
    return (
        "Funciona assim 👇\n\n"
        f"1️⃣ *Internet ilimitada + VPN* — {brl(INTERNET_PRIMEIRO)} no 1º mês "
        f"(depois {brl(INTERNET_DEPOIS)}), com teste grátis de {INTERNET_TRIAL_HORAS}h. "
        "Somente *Android* (não temos iPhone), com chip *TIM* ou *Vivo* e recarga "
        "nos últimos 3 meses.\n\n"
        f"2️⃣ *IPTV Completo* — {brl(IPTV_COMPLETO_PRIMEIRO)} no 1º mês "
        f"(depois {brl(IPTV_COMPLETO_DEPOIS)}), com todos os streamers.\n"
        f"3️⃣ *IPTV Básico* — {brl(IPTV_BASICO_PRIMEIRO)} no 1º mês "
        f"(depois {brl(IPTV_BASICO_DEPOIS)}).\n\n"
        "Qual você quer saber mais? Pode digitar *1*, *2* ou *3*."
    )


def buscar_faq(texto: str) -> str | None:
    """Respostas deterministas para as duvidas mais comuns."""
    if tem(texto, "iphone", "ios", "apple"):
        return sem_iphone()

    if tem(texto, "teste", "gratis", "gratuito", "demonstracao"):
        return faq_teste()

    pergunta_valor = tem(
        texto, "preco", "precos", "valor", "valores", "quanto", "custa", "custo", "mensalidade"
    )
    if pergunta_valor and tem(texto, "iptv", "plano", "completo", "basico", "tv"):
        if extrair_plano_iptv(texto) == "basico" or tem(texto, "basico"):
            primeiro, depois = IPTV_BASICO_PRIMEIRO, IPTV_BASICO_DEPOIS
            return (
                f"O IPTV *Básico* está {brl(primeiro)} no 1º mês e {brl(depois)} depois."
            )
        if extrair_plano_iptv(texto) == "completo" or tem(texto, "completo"):
            primeiro, depois = IPTV_COMPLETO_PRIMEIRO, IPTV_COMPLETO_DEPOIS
            return (
                f"O IPTV *Completo* (todos os streamers) está {brl(primeiro)} no 1º mês "
                f"e {brl(depois)} depois."
            )
        return faq_iptv()
    if pergunta_valor and tem(texto, "internet", "vpn", "chip"):
        return faq_internet()
    if pergunta_valor:
        return faq_internet() + "\n\n" + faq_iptv()

    if tem(texto, "streamer", "streamers", "netflix", "youtube", "prime video", "disney"):
        return faq_streamers()
    if tem(texto, "recarga", "recarregar"):
        return faq_recarga()
    if tem(texto, "operadora", "tim", "vivo", "claro") or (
        tem(texto, "oi") and tem(texto, "chip", "operadora")
    ):
        return faq_operadoras()
    if tem(texto, "aplicativo", "app", "instalar", "play store", "baixar", "download"):
        return faq_aplicativo()
    if tem(texto, "vpn"):
        return faq_vpn()

    if tem(
        texto,
        "como funciona",
        "funciona",
        "me explica",
        "explica",
        "explicar",
        "saber",
        "informacao",
        "informacoes",
        "o que e",
        "o que faz",
    ):
        if tem(texto, "internet", "vpn", "chip"):
            return faq_internet()
        if tem(texto, "iptv", "tv", "streamer"):
            return faq_iptv()
        return explicacao_geral()
    return None
