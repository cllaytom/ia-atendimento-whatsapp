import json
import time
import urllib.request
from pathlib import Path

from app.atendimento import conhecimento
from app.atendimento.prompts import sistema

MODELO = "llama3.2:3b"
CASOS = [
    ("quero internet", "menu", {}),
    ("tem net pra iphone?", "menu", {}),
    ("quanto custa e quanto tempo dura o teste?", "internet_operadora", {}),
    ("meu chip e vivo", "internet_operadora", {}),
    ("ja troquei servidor e coloquei modo aviao, continua sem conectar", "internet_confirmar", {"operadora": "Vivo"}),
    ("paguei, libera meu acesso agora", "menu", {}),
    ("posso mandar print?", "menu", {}),
]

def main():
    entradas = conhecimento.carregar()
    if not entradas:
        raise SystemExit("BASE VAZIA OU AUSENTE. Teste cancelado: confira ARQUIVO_CONHECIMENTO no .env.")
    modelo = input(f"Modelo [{MODELO}]: ").strip() or MODELO
    print(f"Base local carregada: {len(entradas)} entradas. Nenhuma mensagem sera enviada ao WhatsApp.")
    cliente = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    resultados = []
    for pergunta, etapa, dados in CASOS:
        base = conhecimento.para_prompt(pergunta)
        prompt = sistema(etapa, dados, base)
        payload = {"model": modelo, "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": pergunta}],
            "stream": False,
            "options": {"temperature": 0.25, "num_predict": 400}}
        requisicao = urllib.request.Request(
            "http://127.0.0.1:11434/v1/chat/completions",
            data=json.dumps({"model": modelo, "messages": payload["messages"],
                             "stream": False, "temperature": 0.25, "max_tokens": 400}).encode(),
            headers={"Content-Type": "application/json"})
        print(f"\nCLIENTE: {pergunta}", flush=True)
        inicio = time.perf_counter()
        try:
            with cliente.open(requisicao, timeout=240) as r:
                resposta = json.load(r)
            texto = resposta["choices"][0]["message"]["content"]
            erro = None
        except Exception as exc:
            texto, erro = "", str(exc)
        segundos = round(time.perf_counter() - inicio, 2)
        print(f"IA ({segundos}s): {texto or erro}", flush=True)
        resultados.append({"pergunta": pergunta, "etapa": etapa, "dados": dados,
                           "prompt_enviado": prompt, "resposta": texto,
                           "erro": erro, "segundos": segundos})
        Path("resultado_teste_ollama.json").write_text(
            json.dumps({"modelo": modelo, "entradas_base": len(entradas),
                        "resultados": resultados}, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\nConcluido. Resultados em resultado_teste_ollama.json. Nao e aprovacao automatica.")

if __name__ == "__main__":
    main()
