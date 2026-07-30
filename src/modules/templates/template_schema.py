"""Contratos de templates de pipeline salvos pela UI."""

from typing import Any, Dict, List

from modules.pipeline.pipeline_schema import SecaoPipeline
from pydantic import BaseModel, Field, field_validator


class TemplatePipelineEntrada(BaseModel):
    """Payload de gravação de um novo template de pipeline."""

    nome_template: str = Field(min_length=1)
    pipeline_secoes: List[SecaoPipeline] = Field(min_length=1)

    @field_validator("nome_template")
    @classmethod
    def nome_nao_vazio(cls, valor: str) -> str:
        valor = valor.strip()
        if not valor:
            raise ValueError("O nome do template não pode ser vazio.")
        return valor


class TemplatePipelineResposta(BaseModel):
    """Template persistido, devolvido na listagem para a UI."""

    id: str
    nome_template: str
    pipeline_secoes: List[Dict[str, Any]]
