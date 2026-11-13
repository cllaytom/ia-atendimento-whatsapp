from __future__ import annotations

from pydantic import BaseModel, Field, model_validator


class ConversaCriar(BaseModel):
    contato: str = Field(min_length=2, max_length=80, examples=["11999990000"])
    nome: str | None = Field(default=None, max_length=120, examples=["Maria"])
    canal: str = Field(default="simulador", max_length=30)


class MensagemCliente(BaseModel):
    texto: str | None = Field(default=None, max_length=4000)
    imagem: str | None = None

    @model_validator(mode="after")
    def exigir_conteudo(self):
        if not (self.texto or "").strip() and not self.imagem:
            raise ValueError("Envie um texto ou uma imagem.")
        return self


class RespostaHumano(BaseModel):
    texto: str = Field(min_length=1, max_length=4000)


class RespostaDuvida(BaseModel):
    resposta: str = Field(min_length=1, max_length=4000)
    salvar_na_base: bool = True
    enviar_ao_cliente: bool = Field(
        default=False,
        description="Envia a resposta agora para a conversa do cliente.",
    )


class HistoricoAnalise(BaseModel):
    texto: str = Field(min_length=10, max_length=2_000_000)
    negocio: str | None = Field(default=None, max_length=120)
    limite: int = Field(default=200, ge=1, le=1000)


class EntradaConhecimento(BaseModel):
    pergunta: str = Field(min_length=3, max_length=600)
    resposta: str = Field(min_length=3, max_length=4000)
    termos: list[str] | None = None
