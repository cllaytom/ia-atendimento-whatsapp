import os

# Garante que nenhum teste dependa do .env local e que as pausas nao atrasem
# a suite. Precisa rodar antes de qualquer import de app.*.
os.environ["IA_API_KEY"] = ""
os.environ["IA_BASE_URL"] = ""
os.environ["LINK_APP_ANDROID"] = ""
os.environ["APP_IPTV_PADRAO"] = ""
os.environ["ATENDIMENTO_PAUSA_ATIVA"] = "0"
