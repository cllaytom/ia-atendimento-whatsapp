import time
import httpx
from dotenv import dotenv_values

config = dotenv_values(".env")
chave = (config.get("IA_API_KEY") or "").strip()
modelo = (config.get("IA_MODELO") or "").strip()

if not chave or not modelo:
    print("Falta IA_API_KEY ou IA_MODELO no arquivo .env.")
    raise SystemExit(1)

modelo = modelo.removeprefix("models/")
url = (
    "https://generativelanguage.googleapis.com"
    f"/v1beta/models/{modelo}:generateContent"
)

print("Modelo:", modelo)
print("Consultando o Gemini...")

inicio = time.perf_counter()

try:
    resposta = httpx.post(
        url,
        headers={"x-goog-api-key": chave},
        json={
            "contents": [
                {"parts": [{"text": "Responda apenas: TESTE OK"}]}
            ]
        },
        timeout=httpx.Timeout(30.0, connect=10.0),
    )

    print("Tempo:", round(time.perf_counter() - inicio, 2), "segundos")
    print("HTTP:", resposta.status_code)
    print("Resposta:")
    print(resposta.text.replace(chave, "[CHAVE OCULTA]"))

except httpx.TimeoutException as erro:
    print("Tempo:", round(time.perf_counter() - inicio, 2), "segundos")
    print("Tempo de espera excedido:", type(erro).__name__)

except httpx.RequestError as erro:
    print("Falha de conexao:", type(erro).__name__)