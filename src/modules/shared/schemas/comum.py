"""Schemas Pydantic compartilhados entre os módulos da API."""

from pydantic import BaseModel


class MensagemResponse(BaseModel):
    """Resposta genérica de confirmação de operação."""

    mensagem: str
