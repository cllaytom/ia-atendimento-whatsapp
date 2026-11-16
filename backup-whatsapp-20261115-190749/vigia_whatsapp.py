"""Vigia do WhatsApp real para o atendimento automatico (canal nao oficial).

Ele abre o WhatsApp Web num navegador proprio (o perfil fica salvo em
dados/whatsapp-perfil, entao o login e feito uma vez so), observa as conversas
abertas, entrega cada mensagem nova de cliente para o agente do projeto
(ponte_whatsapp) e envia as respostas de volta.

Como rodar (uma vez, para escanear o QR):

    python -m app.atendimento.vigia_whatsapp --login

Depois, sempre que quiser o atendimento no ar (terminal proprio):

    python -m app.atendimento.vigia_whatsapp

Enquanto ele estiver rodando, o agente responde sozinho. Ao fechar o terminal,
o atendimento automatico para.

Cuidados de seguranca contra banimento (o numero e o de atendimento):
- pausa variavel antes de cada envio (config do ATENDIMENTO_PAUSA_*)
- nao responde a mensagem enviada por voce mesmo
- nao reenvia a mesma mensagem duas vezes (controle por id interno)
- conversa que voce assumir no painel (estado humano) nao e respondida
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import random
import re
import sys
import time
from pathlib import Path

from . import config
from . import ponte_whatsapp

logger = logging.getLogger("atendimento.vigia")

PERFIL = config.ARQUIVO_CONHECIMENTO.parent / "whatsapp-perfil"
ESTADO = config.ARQUIVO_CONHECIMENTO.parent / "whatsapp-vigia.json"
INTERVALO = float(os.getenv("WHATSAPP_INTERVALO", "6"))
# Teto de conversas atendidas por ciclo, para nunca sair respondendo em massa.
MAX_POR_CICLO = int(os.getenv("WHATSAPP_MAX_POR_CICLO", "3"))
IGNORAR = {
    nome.strip().lower()
    for nome in os.getenv("WHATSAPP_IGNORAR", "").split(",")
    if nome.strip()
}


def _estado() -> dict:
    try:
        return json.loads(ESTADO.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"vistos": [], "ativos": []}


def _salvar_estado(dados: dict) -> None:
    dados["vistos"] = dados.get("vistos", [])[-400:]
    ESTADO.write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")


def _pausa_humana(texto: str) -> None:
    if not config.PAUSA_ATIVA:
        return
    tempo = config.PAUSA_MIN + len(texto or "") * config.PAUSA_POR_CARACTERE
    tempo = min(tempo, config.PAUSA_TETO)
    tempo += random.uniform(0, 0.6)
    time.sleep(tempo)


def _eh_numero(nome: str) -> bool:
    return bool(re.fullmatch(r"[\d\s()+-]+", nome or ""))


def _montar_opcoes() -> "Options":
    """Opcoes do Chrome usando o perfil salvo do WhatsApp.

    O perfil so aceita uma janela por vez; o vigia e o dono dele.
    """
    from selenium.webdriver.chrome.options import Options

    opcoes = Options()
    for caminho in (
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
    ):
        if Path(caminho).exists():
            opcoes.binary_location = caminho
            break
    opcoes.add_argument(f"--user-data-dir={PERFIL}")
    opcoes.add_argument("--profile-directory=Default")
    opcoes.add_argument("--start-maximized")
    opcoes.add_argument("--disable-notifications")
    opcoes.add_argument("--no-first-run")
    opcoes.add_argument("--no-default-browser-check")
    opcoes.add_experimental_option("excludeSwitches", ["enable-automation"])
    opcoes.add_experimental_option("useAutomationExtension", False)
    return opcoes


def start(login: bool = False):
    """Abre o navegador no WhatsApp Web com perfil persistente."""
    from selenium import webdriver

    driver = webdriver.Chrome(options=_montar_opcoes())
    driver.get("https://web.whatsapp.com")
    logger.info("WhatsApp Web aberto. Perfil: %s", PERFIL)
    if login:
        print("Escaneie o QR code com o WhatsApp do celular (Aparelhos conectados).")
        print("O navegador vai se fechar sozinho quando o login terminar.")
        limite = time.time() + float(os.getenv("WHATSAPP_LOGIN_ESPERA", "300"))
        while time.time() < limite:
            if _conversas_visiveis(driver):
                print("Login confirmado: perfil salvo em", PERFIL)
                return driver
            time.sleep(2)
        print("Tempo esgotado sem login. Rode novamente com --login.")
    return driver


def _conversas_visiveis(driver) -> list[tuple[str, bool]]:
    """Conversas da lista: (nome, tem_mensagem_nao_lida).

    Lido por JS: o Selenium devolve elementos que ficam "stale" quando a lista
    se redesenha. O nome do contato e o span[title] dentro da celula da grade.
    A mensagem nao lida aparece como contagem no fim do texto da celula.
    """
    try:
        linhas = driver.execute_script(
            """
            const saida = [];
            const vistos = new Set();
            for (const span of document.querySelectorAll('#pane-side span[title]')) {
                const nome = span.getAttribute('title');
                if (!nome || nome.length > 40) continue;
                // Sobe ate a celula que tem o texto completo da linha.
                let celula = span;
                for (let i = 0; i < 10 && celula; i++) {
                    const t = celula.innerText;
                    if (celula.tagName === 'DIV' && t && t.split('\n').length > 2) break;
                    celula = celula.parentElement;
                }
                if (!celula) continue;
                const limpo = nome.replace(/[\u202a\u202c]/g, '').trim();
                if (!limpo || vistos.has(limpo)) continue;
                vistos.add(limpo);
                const partes = (celula.innerText || '').split('\n').map(x => x.trim()).filter(Boolean);
                const ultima = partes[partes.length - 1] || '';
                const naoLida = /^[0-9]+$/.test(ultima);
                saida.push([limpo, naoLida]);
            }
            return saida;
            """
        ) or []
    except Exception:
        return []
    conversas: list[tuple[str, bool]] = []
    for nome, nao_lida in linhas:
        if nome:
            conversas.append((nome, bool(nao_lida)))
    return conversas


def _abrir(driver, nome: str) -> bool:
    """Abre a conversa pelo nome, clicando no elemento no proprio navegador.

    O clique acontece dentro do JS: a lista do WhatsApp se redesenha sozinha e
    o elemento devolvido pelo Selenium fica "stale" antes do clique.
    """
    try:
        clicou = driver.execute_script(
            """
            const alvo = arguments[0];
            const spans = document.querySelectorAll('#pane-side span[title]');
            for (const span of spans) {
                if (span.getAttribute('title') !== alvo) continue;
                // A lista e uma grade virtual (div.row / div.gridcell): nao ha
                // role=listitem. O clique tem de ser disparado na celula.
                let alvoClique = span;
                let n = span;
                for (let i = 0; i < 8 && n; i++) {
                    if (n.tagName === 'DIV' && (n.classList.contains('gridcell') || n.classList.contains('row'))) {
                        alvoClique = n; break;
                    }
                    n = n.parentElement;
                }
                alvoClique.scrollIntoView({block: 'center'});
                for (const tipo of ['mousedown', 'mouseup', 'click']) {
                    alvoClique.dispatchEvent(new MouseEvent(tipo, {bubbles: true, cancelable: true, view: window}));
                }
                return true;
            }
            return false;
            """,
            nome,
        )
        if not clicou:
            return False
        time.sleep(1.5)
        return True
    except Exception:
        return False


def _mensagens_da_conversa(driver) -> list[dict]:
    """Le as mensagens da conversa aberta (layout novo do WhatsApp Web 2026).

    Cada mensagem tem `data-pre-plain-text` = "[hora, data] Autor: " e o texto
    dentro de `div.copyable-text`. Mensagem sem esse atributo foi enviada por
    mim (aparece so como "Você:"), entao o texto e usado para reconhecer a
    ultima mensagem do cliente.
    """
    from selenium.webdriver.common.by import By

    mensagens: list[dict] = []
    try:
        blocos = driver.find_elements(By.CSS_SELECTOR, "#main div[data-id]")
    except Exception:
        return mensagens
    for bloco in blocos[-20:]:
        try:
            texto = bloco.find_element(By.CSS_SELECTOR, "div.copyable-text").text.strip()
        except Exception:
            continue
        if not texto:
            continue
        try:
            marca = bloco.find_element(By.CSS_SELECTOR, "[data-pre-plain-text]")
            autor = marca.get_attribute("data-pre-plain-text") or ""
        except Exception:
            autor = ""
        meu = not autor.strip()
        mensagens.append({"meu": meu, "texto": texto, "autor": autor.strip()})
    return mensagens


def _responder(driver, texto: str) -> None:
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys

    _pausa_humana(texto)
    caixas = driver.find_elements(By.CSS_SELECTOR, "footer div[contenteditable='true']")
    if not caixas:
        raise RuntimeError("Caixa de mensagem nao encontrada.")
    caixa = caixas[-1]
    caixa.click()
    for linha in (texto or "").split("\n"):
        caixa.send_keys(linha)
        caixa.send_keys(Keys.SHIFT, Keys.ENTER)
    caixa.send_keys(Keys.ENTER)


def rodar() -> None:
    from selenium.common.exceptions import WebDriverException

    driver = start(login=False)
    dados = _estado()
    logger.info("Vigia iniciado. Intervalo: %ss", INTERVALO)
    if not _conversas_visiveis(driver):
        logger.warning("Lista de conversas nao encontrada: login pode ter caido.")
        return

    if not dados.get("linha_base"):
        # Primeira execucao: nada do que ja esta no WhatsApp e respondido.
        # Só mensagem que chegar DEPOIS deste ponto vai para o agente.
        base: list[str] = []
        for nome, _nao_lida in _conversas_visiveis(driver):
            if not _abrir(driver, nome):
                continue
            mensagens = _mensagens_da_conversa(driver)
            if mensagens:
                base.append(f"{nome}|{mensagens[-1]['texto'][:120]}")
        dados["linha_base"] = base
        _salvar_estado(dados)
        logger.info("Linha de base criada: %s conversas ja existentes ignoradas.", len(base))
    try:
        while True:
            try:
                novas_no_ciclo = 0
                for nome, nao_lida in _conversas_visiveis(driver):
                    if nome.lower() in IGNORAR:
                        continue
                    # Sem selo de nao lida nao ha mensagem nova do cliente:
                    # economiza abrir conversa e evita responder coisa antiga.
                    if not nao_lida:
                        continue
                    if not _abrir(driver, nome):
                        continue
                    mensagens = _mensagens_da_conversa(driver)
                    if not mensagens:
                        continue
                    ultima = mensagens[-1]
                    if ultima["meu"]:
                        continue
                    chave = f"{nome}|{ultima['texto'][:120]}"
                    if chave in dados["vistos"] or chave in dados.get("linha_base", []):
                        continue
                    dados["vistos"].append(chave)
                    _salvar_estado(dados)

                    try:
                        resultado = ponte_whatsapp.receber(
                            contato=nome, texto=ultima["texto"], nome=nome
                        )
                    except Exception:
                        logger.exception("Falha ao processar mensagem de %s", nome)
                        continue

                    for resposta in resultado["respostas"]:
                        try:
                            _responder(driver, resposta)
                            logger.info("Respondido para %s: %s", nome, resposta[:60])
                        except Exception:
                            logger.exception("Falha ao responder %s", nome)
                    if resultado["alerta_humano"]:
                        logger.warning("Transferencia: %s | %s", nome, resultado.get("motivo"))
                    novas_no_ciclo += 1
                    if novas_no_ciclo >= MAX_POR_CICLO:
                        logger.info("Limite de %s respostas por ciclo atingido.", MAX_POR_CICLO)
                        break
                time.sleep(INTERVALO)
            except WebDriverException:
                logger.warning("Navegador fechado ou desconectado; encerrando.")
                break
    finally:
        try:
            driver.quit()
        except Exception:
            pass


def main() -> int:
    parser = argparse.ArgumentParser(description="Atendimento automatico no WhatsApp Web")
    parser.add_argument("--login", action="store_true", help="Abrir para escanear o QR e sair")
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    if args.login:
        driver = start(login=True)
        driver.quit()
        return 0
    rodar()
    return 0


if __name__ == "__main__":
    sys.exit(main())
