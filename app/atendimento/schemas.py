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


class EntradaConhecimento(BaseModel):
    pergunta: str = Field(min_length=3, max_length=600)
    resposta: str = Field(min_length=3, max_length=4000)
    termos: list[str] | None = None
