"""Leitura da planilha de numeros enviada pelo painel.

Somente leitura: o arquivo chega pela requisicao e nada e gravado em disco.
A saida e uma lista de linhas "telefone;nome;produto;vencimento", no mesmo
formato aceito pela caixa de colar. A gravacao fica em servico.adicionar_numeros,
que aplica as guardas da campanha (opt-out, cooldown, 12 digitos, etc.).
"""

from __future__ import annotations

import csv
import io
import unicodedata
from datetime import date, datetime, timedelta

from .contatos import normalizar

MAXIMO = 20000
EXTENSOES = (".xlsx", ".xlsm", ".xlsb", ".csv", ".txt", ".tsv")

# Nomes de coluna aceitos (comparados sem acento, minusculo e sem simbolos).
ALIASES = {
    "telefone": (
        "telefone", "telefones", "celular", "celulares", "numero", "numeros",
        "whatsapp", "whats", "fone", "tel", "phone", "contato",
    ),
    "nome": ("nome", "nomes", "cliente", "clientes", "usuario", "usuarios"),
    "produto": ("produto", "produtos", "plano", "servico", "servicos"),
    "vencimento": (
        "vencimento", "vencimentos", "venc", "vencimentoem", "datadevencimento",
        "dtvencimento", "dtvenc",
    ),
}


class PlanilhaInvalida(RuntimeError):
    """Arquivo ilegivel, vazio ou em formato nao suportado."""


def _chave(texto) -> str:
    """'Telefone Celular' -> 'telefonecelular' (sem acento e sem simbolos)."""
    base = unicodedata.normalize("NFKD", str(texto or ""))
    base = "".join(c for c in base if not unicodedata.combining(c))
    return "".join(c for c in base.lower() if c.isalnum())


def _texto(valor) -> str:
    if valor is None:
        return ""
    if isinstance(valor, datetime):
        return valor.strftime("%d/%m/%Y")
    if isinstance(valor, date):
        return valor.strftime("%d/%m/%Y")
    if isinstance(valor, float) and valor.is_integer():
        return str(int(valor))
    return str(valor).strip()


def data_iso(texto: str) -> str:
    """dd/mm/aaaa ou aaaa-mm-dd viram aaaa-mm-dd; resto volta como veio."""
    bruto = (texto or "").strip()
    if not bruto:
        return ""
    if bruto.isdigit() and 20000 <= int(bruto) <= 80000:
        # Numero de serie do Excel (dias desde 30/12/1899).
        try:
            return (date(1899, 12, 30) + timedelta(days=int(bruto))).isoformat()
        except (ValueError, OverflowError):
            return bruto
    for formato in ("%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(bruto, formato).date().isoformat()
        except ValueError:
            continue
    return bruto


def _ler_xlsx(conteudo: bytes) -> list[list]:
    try:
        from openpyxl import load_workbook
    except ImportError as erro:  # pragma: no cover - dependencia do requirements
        raise PlanilhaInvalida("openpyxl nao instalado neste ambiente") from erro
    try:
        pasta = load_workbook(io.BytesIO(conteudo), read_only=True, data_only=True)
    except Exception as erro:
        raise PlanilhaInvalida("nao foi possivel abrir o .xlsx: " + str(erro)) from erro
    try:
        return [list(linha) for linha in pasta.active.iter_rows(values_only=True)]
    finally:
        pasta.close()


def _ler_xlsb(conteudo: bytes) -> list[list]:
    try:
        from pyxlsb import open_workbook
    except ImportError as erro:  # pragma: no cover - dependencia do requirements
        raise PlanilhaInvalida("pyxlsb nao instalado neste ambiente") from erro
    try:
        with open_workbook(io.BytesIO(conteudo)) as pasta:
            with pasta.get_sheet(1) as aba:
                return [[celula.v for celula in linha] for linha in aba.rows()]
    except Exception as erro:
        raise PlanilhaInvalida("nao foi possivel abrir o .xlsb: " + str(erro)) from erro


def _ler_csv(conteudo: bytes) -> list[list]:
    texto = None
    for codificacao in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            texto = conteudo.decode(codificacao)
            break
        except UnicodeDecodeError:
            continue
    if texto is None:  # pragma: no cover - latin-1 aceita qualquer byte
        raise PlanilhaInvalida("codificacao do CSV nao reconhecida")

    amostra = texto[:4096]
    try:
        dialeto = csv.Sniffer().sniff(amostra, delimiters=";,\t|")
    except csv.Error:
        dialeto = csv.excel
        dialeto.delimiter = "\t" if "\t" in amostra else (";" if ";" in amostra else ",")
    return [linha for linha in csv.reader(io.StringIO(texto), dialeto)]


def _mapear_cabecalho(primeira: list) -> dict[str, int]:
    """Descobre em quais colunas estao telefone/nome/produto/vencimento."""
    mapa: dict[str, int] = {}
    for indice, celula in enumerate(primeira):
        chave = _chave(celula)
        if not chave:
            continue
        for campo, nomes in ALIASES.items():
            if campo in mapa:
                continue
            if any(nome in chave for nome in nomes):
                mapa[campo] = indice
                break
    return mapa if "telefone" in mapa else {}


def _telefone_da_linha(linha: list, coluna: int | None) -> tuple[int | None, str | None]:
    ordem = ([coluna] if coluna is not None else []) + [
        indice for indice in range(len(linha)) if indice != coluna
    ]
    for indice in ordem:
        if indice is None or indice >= len(linha):
            continue
        numero = normalizar(_texto(linha[indice]))
        if numero:
            return indice, numero
    return None, None


def _valor(linha: list, indice: int | None) -> str:
    if indice is None or indice >= len(linha):
        return ""
    return _texto(linha[indice])


def ler(conteudo: bytes, nome: str) -> dict:
    """Le a planilha e devolve as linhas prontas para a caixa do painel."""
    if not conteudo:
        raise PlanilhaInvalida("o arquivo esta vazio")

    extensao = ("." + nome.rsplit(".", 1)[-1].lower()) if "." in (nome or "") else ""
    if extensao in (".xlsx", ".xlsm"):
        bruto = _ler_xlsx(conteudo)
    elif extensao == ".xlsb":
        bruto = _ler_xlsb(conteudo)
    elif extensao in (".csv", ".txt", ".tsv"):
        bruto = _ler_csv(conteudo)
    else:
        raise PlanilhaInvalida("formato nao suportado: use .xlsx, .xlsb ou .csv")

    bruto = [linha for linha in bruto if any(_texto(celula) for celula in linha)]
    if not bruto:
        raise PlanilhaInvalida("a planilha esta vazia")

    colunas = _mapear_cabecalho(bruto[0])
    corpo = bruto[1:] if colunas else bruto

    saida: list[str] = []
    sem_telefone = 0
    cortado = False

    for linha in corpo:
        indice_tel, telefone = _telefone_da_linha(linha, colunas.get("telefone"))
        if not telefone:
            sem_telefone += 1
            continue

        if colunas:
            nome = _valor(linha, colunas.get("nome"))
            produto = _valor(linha, colunas.get("produto"))
            vencimento = data_iso(_valor(linha, colunas.get("vencimento")))
        else:
            restantes = [
                _texto(valor)
                for indice, valor in enumerate(linha)
                if indice != indice_tel and _texto(valor)
            ]
            nome = restantes[0] if len(restantes) > 0 else ""
            produto = restantes[1] if len(restantes) > 1 else ""
            vencimento = data_iso(restantes[2]) if len(restantes) > 2 else ""

        campos = [telefone]
        extras = [campo.replace(";", " ").replace("\n", " ") for campo in (nome, produto, vencimento)]
        while extras and not extras[-1]:
            extras.pop()
        campos.extend(extras)
        saida.append(";".join(campos))

        if len(saida) >= MAXIMO:
            cortado = True
            break

    if not saida:
        raise PlanilhaInvalida(
            "nenhum telefone reconhecido na planilha (confira a coluna de telefone)"
        )

    return {
        "linhas": "\n".join(saida),
        "total": len(saida),
        "sem_telefone": sem_telefone,
        "cabecalho": bool(colunas),
        "colunas": {campo: indice + 1 for campo, indice in colunas.items()},
        "cortado": cortado,
    }
