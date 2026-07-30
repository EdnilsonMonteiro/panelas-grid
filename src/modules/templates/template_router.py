"""Rotas de templates de pipeline (/api/templates)."""

import sqlite3
from typing import List

from core.dependencies import get_db
from fastapi import APIRouter, Depends, HTTPException
from modules.shared.schemas.comum import MensagemResponse
from modules.templates.template_schema import (
    TemplatePipelineEntrada,
    TemplatePipelineResposta,
)

from . import template_service

router = APIRouter(prefix="/api/templates", tags=["templates"])


@router.get("", response_model=List[TemplatePipelineResposta])
def listar_templates(
    conn: sqlite3.Connection = Depends(get_db),
) -> List[TemplatePipelineResposta]:
    """Retorna todos os modelos de pipelines salvos para alimentar o dropdown da UI."""
    try:
        return template_service.listar_templates(conn)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("", response_model=MensagemResponse, status_code=201)
def salvar_template(
    dados: TemplatePipelineEntrada, conn: sqlite3.Connection = Depends(get_db)
) -> MensagemResponse:
    """Grava um novo modelo configurado pela UI no banco."""
    try:
        template_service.salvar_template(conn, dados)
        return MensagemResponse(mensagem="Modelo gravado com sucesso!")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.delete("/{id_template}", response_model=MensagemResponse)
def deletar_template(
    id_template: int, conn: sqlite3.Connection = Depends(get_db)
) -> MensagemResponse:
    """Remove um modelo de pipeline do banco de dados."""
    try:
        template_service.deletar_template(conn, id_template)
        return MensagemResponse(mensagem="Modelo deletado com sucesso!")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
