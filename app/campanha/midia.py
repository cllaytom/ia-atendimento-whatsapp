"""Midia da campanha (fase 2): catalogo local, sem envio.

Este modulo apenas OLHA arquivos dentro de config.MIDIA_PASTA. Ele nao abre
conexao, nao usa a ponte do WhatsApp, nao importa nada de rede e nao envia
nada. Serve para voce aprovar a imagem antes de qualquer conector existir.

Regra de ouro: a imagem so acompanha mensagens de resposta, nunca o primeiro
contato (config.MIDIA_NO_PRIMEIRO_CONTATO = False).
"""

from __future__ import annotations

from pathlib import Path

from . import config, mensagens


def pasta() -> Path:
    return Path(config.MIDIA_PASTA)


def _dentro_da_pasta(caminho: Path) -> bool:
    """Impede que o nome escape da pasta aprovada (../, caminho absoluto etc.)."""
    try:
        caminho.resolve().relative_to(pasta().resolve())
        return True
    except ValueError:
        return False


def resolver(nome: str) -> Path | None:
    """Caminho absoluto de uma imagem da pasta aprovada, ou None."""
    nome = (nome or "").strip()
    if not nome or nome.startswith(".") or "/" in nome or "\\" in nome:
        return None
    alvo = pasta() / nome
    if not _dentro_da_pasta(alvo) or not alvo.is_file():
        return None
    return alvo


def validar(caminho: Path) -> dict:
    """Confere formato e tamanho. Nao converte, nao move e nao envia."""
    if not caminho.is_file():
        return {"arquivo": caminho.name, "ok": False, "motivo": "arquivo ausente"}

    formato = caminho.suffix.lower().lstrip(".")
    bytes_ = caminho.stat().st_size
    limite = config.MIDIA_TAMANHO_MAX_MB * 1024 * 1024
    problemas: list[str] = []
    if formato not in config.MIDIA_FORMATOS:
        problemas.append(f"formato .{formato} nao aprovado")
    if bytes_ > limite:
        problemas.append(
            f"{bytes_ / 1024 / 1024:.1f} MB acima do limite de "
            f"{config.MIDIA_TAMANHO_MAX_MB} MB"
        )

    dados = {
        "arquivo": caminho.name,
        "formato": formato,
        "bytes": bytes_,
        "kb": round(bytes_ / 1024, 1),
        "ok": not problemas,
        "motivo": "; ".join(problemas),
    }
    # PNG de foto pesa muito; avisa sem bloquear.
    if dados["ok"] and formato in ("png", "webp") and bytes_ > 600 * 1024:
        dados["motivo"] = "arquivo grande para foto: converta para JPG (250-400 KB)"
    return dados


def listar() -> dict:
    """Imagens aprovadas na pasta, com tamanho e validacao."""
    diretorio = pasta()
    itens: list[dict] = []
    if diretorio.is_dir():
        for caminho in sorted(diretorio.iterdir(), key=lambda p: p.name.lower()):
            if not caminho.is_file():
                continue
            if caminho.suffix.lower().lstrip(".") not in config.MIDIA_FORMATOS:
                continue
            itens.append(validar(caminho))

    return {
        "habilitada": config.MIDIA_HABILITADA,
        "no_primeiro_contato": config.MIDIA_NO_PRIMEIRO_CONTATO,
        "pasta": str(diretorio),
        "limite_mb": config.MIDIA_TAMANHO_MAX_MB,
        "itens": itens,
        "total": len(itens),
        "legenda": _legenda(mensagens.legenda_padrao()),
        "aviso": (
            "Somente leitura. Nada e enviado: a imagem so acompanha a resposta "
            "ao cliente, depois que ele falar com voce."
        ),
    }


def _legenda(texto: str) -> dict:
    final = mensagens.garantir_optout((texto or "").strip())
    return {
        "texto": final,
        "caracteres": len(final),
        "limite": config.MIDIA_LIMITE_LEGENDA,
        "ok": len(final) <= config.MIDIA_LIMITE_LEGENDA,
    }


def legenda(texto: str = "", extra: str = "") -> dict:
    """Legenda pronta para acompanhar o flyer, com opt-out garantido."""
    if texto.strip():
        return _legenda(texto)
    return _legenda(mensagens.legenda_padrao(extra))
