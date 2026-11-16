"""Regras puras de suporte; sem rede, banco ou envio de mensagens."""
import re
import unicodedata

def normalizar(texto):
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode().lower()).strip()

def possui(texto, termos):
    return any(re.search(r"(?<!\w)" + re.escape(t) + r"(?!\w)", texto) for t in termos)

FALHAS = ("nao funciona", "nao esta funcionando", "nao ta funcionando", "nao conecta", "nao conectou", "nao quer conectar", "sem internet", "sem conexao", "conectando", "parou", "lento", "lenta", "travando", "nao carrega", "nao esta conectado", "nao ta pegando", "nao esta pegando")
AVISO = "Aguarde um momento, nossa equipe está verificando sua solicitação"
REDE = "Com o Wi-Fi desligado e os dados móveis ligados, qual símbolo aparece ao lado do sinal do chip: 5G, 4G/LTE, H+, H, G, E ou nenhum? Responda por texto."
PASSOS = {
 "dados": "Para testar a internet do chip, desligue o Wi-Fi e mantenha os dados móveis ligados no chip usado pelo serviço. Confira se há sinal e tente conectar. Qual foi o resultado?",
 "aviao": "Se puder interromper a conexão por um momento, ative o modo avião por cerca de 30 segundos e depois desative. Confira os dados móveis e me diga qual símbolo de rede apareceu e se conseguiu navegar.",
 "local": "Tente um local próximo com melhor recepção, sem se expor a chuva forte, trânsito ou outros riscos. Depois me diga qual símbolo de rede apareceu. Não precisa sair para uma área exposta durante uma tempestade.",
 "reinicio": "Se puder interromper o uso por um momento, reinicie o celular. Depois confira os dados móveis e me diga qual rede apareceu e se conseguiu navegar.",
 "servidor": "No aplicativo atual, selecione outro servidor da operadora do seu chip e tente conectar. Faça uma tentativa por vez. Qual foi o resultado?",
 "atualizacao": "Se ainda não atualizou as configurações do aplicativo atual, use uma rede Wi-Fi disponível para atualizar. Depois desligue o Wi-Fi, deixe os dados móveis ligados e teste. Se não encontrar essa opção, descreva por texto o que aparece. Não desinstale nem troque o aplicativo.",
}
CHUVA = "Chuva forte pode contribuir para oscilações na rede, mas não confirma a causa. A conexão celular comum usa antenas terrestres, não um sinal direto de satélite. Vamos conferir o sinal e as tentativas realizadas. "

ENSINOS = [
 ("Qual a primeira verificação quando a VPN não conecta?", REDE),
 ("Como testar a VPN pelos dados móveis?", PASSOS["dados"]),
 ("O que orientar com H, G, E ou sem sinal?", "Para este serviço, priorize recuperar um sinal adequado: modo avião, mudança segura de local e reinício, sem repetir tentativas. Não insista em servidores enquanto falta rede adequada."),
 ("Como orientar o modo avião?", PASSOS["aviao"]),
 ("Como orientar mudança de local?", PASSOS["local"]),
 ("Quando orientar reiniciar o celular?", PASSOS["reinicio"]),
 ("Como testar outro servidor da operadora?", PASSOS["servidor"]),
 ("Como atualizar configurações da VPN?", PASSOS["atualizacao"]),
 ("Como tratar H+ no nosso serviço?", "Considere a limitação de desempenho informada para este serviço e tente recuperar 4G/LTE ou 5G. Não confunda isso com uma regra universal de ausência de dados em H, G ou E."),
 ("Como tratar tentativas de suporte já realizadas?", "Leia o histórico e registre as tentativas. Não repita modo avião, reinício ou testes de servidores já concluídos. Oriente uma etapa aplicável por vez e aguarde o resultado."),
 ("Como confirmar que o suporte resolveu?", "Peça a confirmação de navegação pelos dados móveis, com Wi-Fi desligado. Apenas aparecer conectado na VPN não comprova navegação. Não ofereça contratação durante o suporte."),
 ("Chuva ou tempo nublado explica falha na VPN?", CHUVA + "Não afirme queda geral ou instabilidade regional sem confirmação atual."),
]
PENDENCIAS = [
 ("Qual procedimento aprovado resolve quando a VPN só funciona com saldo da operadora?", "Os históricos não demonstram causa única. Não impor recarga como solução universal."),
 ("Qual integração autorizada permite consultar validade e autenticação?", "Não confirmar renovação, liberação ou alteração de credenciais sem execução verificável."),
 ("Qual fonte atual confirma indisponibilidade por operadora/servidor?", "Não usar relatos históricos para afirmar incidente ou normalidade atual."),
 ("Qual caminho textual atualiza as configurações no aplicativo atualmente aprovado?", "Usar somente o aplicativo configurado; não reaproveitar links ou posições de botões antigos."),
]

def rede_em(texto):
    if possui(texto, ("sem sinal", "nenhum sinal", "nenhum", "sem rede")): return "sem_sinal"
    match = re.search(r"(?<!\w)(5g|4g|lte|h\+|h|g|e)(?!\w)", texto)
    if match and (match.group(1) not in {"e", "h", "g"} or texto.strip(" .!?") == match.group(1) or re.search(r"(?:rede|aparece|sinal|fica|ficou|esta em|so tem)\s+(?:em\s+)?" + re.escape(match.group(1)) + r"\b", texto)):
        return "4g" if match.group(1) == "lte" else match.group(1)
    return None

def avancar(texto, anterior=None, servico="", historico=()):
    t = normalizar(texto)
    state = dict(anterior or {})
    done = set(state.get("feitos", []))
    internet = possui(t, ("internet", "internete", "vpn", "chip", "celular", "dados moveis"))
    tv = possui(t, ("iptv", "tv", "televisao"))
    service = "iptv" if tv and not internet else "internet" if internet and not tv else servico
    if tv and internet: service = ""
    state["servico"] = service
    def out(resposta, acao="responder"):
        state["feitos"] = sorted(done)
        return {"resposta": resposta, "acao": acao, "estado": state}
    if possui(t, ("falar com atendente", "falar com humano", "quero um atendente", "quero falar com a equipe")):
        return out(AVISO, "transferir")
    active = bool(state.get("ativo")) or possui(t, FALHAS) or possui(t, ("sem sinal", "sem rede", "erro de autenticacao", "senha incorreta", "redefinir senha", "trocar minha senha", "recuperar meu login", "paguei e nao liberou"))
    if not active: return None
    state["ativo"] = True
    if not service: return out("O problema é na internet do celular (VPN) ou no IPTV/TV?")
    if service != "internet": return out("Qual mensagem de erro aparece no IPTV e em qual aparelho? Descreva por texto.", "delegar_iptv")
    if possui(t, ("redefinir senha", "trocar minha senha", "recuperar meu login", "paguei e nao liberou", "senha incorreta", "erro de autenticacao")):
        return out(AVISO, "transferir")
    if possui(t, ("nao encontro a opcao", "nao acho a opcao", "nao sei atualizar")):
        return out("Qual é o nome do aplicativo atual e o texto que aparece na tela? Não desinstale nem troque o app. Se essa opção não puder ser identificada por texto, a equipe precisará conferir.")
    pending = state.get("pendente")
    # Apenas mensagens do cliente e apenas tentativas afirmadas, nao suposicoes.
    for raw in [*historico, texto]:
        for phrase in re.split(r"[,;.!?\n]|\bmas\b", normalizar(raw)):
            if possui(phrase, ("nao fiz", "nao tentei", "nao testei", "nao reiniciei", "nao atualizei", "ainda nao")): continue
            if not possui(phrase, ("ja", "fiz", "tentei", "testei", "reiniciei", "atualizei", "coloquei", "mudei", "desliguei")): continue
            for step, terms in {"aviao":("modo aviao",), "reinicio":("reiniciei", "reiniciar"), "servidor":("servidores", "servidor"), "atualizacao":("atualizei", "atualizado"), "dados":("wifi desligado", "desliguei o wifi", "dados moveis ligados"), "local":("mudei de local", "outro local")}.items():
                if possui(phrase, terms): done.add(step)
    network = rede_em(t)
    if network: state["rede"] = network
    if possui(t, ("voltou a funcionar", "agora funciona", "estou navegando", "abriu o site", "navegando normalmente")) and not possui(t, ("nao voltou", "nao abriu", "so no wifi", "com wifi")):
        state["pendente"] = "confirmar_navegacao"
        return out("Consegue navegar com o Wi-Fi desligado e os dados móveis ligados? Quero confirmar o teste pela rede do chip.")
    if pending == "confirmar_navegacao" and possui(t, ("sim", "isso", "consegui", "normal")) and not possui(t, ("nao", "wifi ligado")):
        state.update(ativo=False, pendente=None)
        return out("Ótimo, navegação confirmada pelos dados móveis. Se precisar, pode nos chamar novamente.")
    if possui(t, ("conectou", "conectado")) and not possui(t, ("nao", "sem internet", "nao carrega", "mas")):
        state["pendente"] = "confirmar_navegacao"
        return out("A VPN conectou. Agora consegue abrir um site com o Wi-Fi desligado e os dados móveis ligados?")
    if pending in PASSOS:
        if t in {"nao", "não"}: return out("Você não conseguiu fazer essa tentativa ou fez e ela não resolveu?")
        if t in {"ok", "certo", "vou tentar", "vou fazer"}: return out("Certo. Faça quando puder e me conte o resultado antes de seguirmos.")
        if possui(t, ("ainda nao fiz", "nao tentei", "nao fiz", "nao posso agora")): return out("Tudo bem. Quando puder realizar essa tentativa com segurança, me diga o resultado. Não precisa repetir as etapas anteriores.")
        if possui(t, ("fiz", "sim", "nao resolveu", "nao funcionou", "continua", "nada", "nao mudou")) or network:
            done.add(pending)
            state["pendente"] = None
    if not state.get("rede"):
        state["pendente"] = "rede"
        return out((CHUVA if possui(t,("chuva", "chovendo", "nublado")) else "") + REDE)
    poor = state["rede"] in {"h", "g", "e", "sem_sinal", "h+"}
    steps = ("aviao", "local", "reinicio") if poor else ("dados", "aviao", "servidor", "atualizacao", "reinicio")
    if not poor and not state.get("operadora"):
        if possui(t,("tim",)): state["operadora"] = "TIM"
        elif possui(t,("vivo",)): state["operadora"] = "Vivo"
        elif pending == "operadora" and possui(t,("claro", "outra")): return out("Neste serviço usamos TIM ou Vivo. Qual dos seus chips está selecionado para os dados móveis?")
        else:
            state["pendente"] = "operadora"
            return out("O chip usado nos dados móveis é TIM ou Vivo?")
    for step in steps:
        if step not in done:
            state["pendente"] = step
            return out(PASSOS[step])
    state["pendente"] = None
    if poor:
        return out("O sinal ainda não está adequado ao nosso serviço. Não vou repetir as tentativas nem insistir em servidores agora. Quando houver 4G/LTE ou 5G, me avise para retomarmos o teste. H+ pode apresentar desempenho reduzido.")
    return out(AVISO, "transferir")
