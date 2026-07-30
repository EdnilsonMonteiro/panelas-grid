"""Rotas de catálogos de travessas/cubas (/api/catalogos)."""

import sqlite3
from typing import Any, Dict, List

from core.dependencies import get_db
from fastapi import APIRouter, Depends, HTTPException
from modules.catalogos.catalogo_schema import ItemCatalogo
from modules.shared.schemas.comum import MensagemResponse

from . import catalogo_service

router = APIRouter(prefix="/api/catalogos", tags=["catalogos"])


@router.get("", response_model=List[str])
def listar_catalogos(conn: sqlite3.Connection = Depends(get_db)) -> List[str]:
    """Retorna os nomes de todos os catálogos disponíveis."""
    try:
        return catalogo_service.listar_nomes_catalogos(conn)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/{nome_catalogo}", response_model=List[Dict[str, Any]])
def obter_itens_catalogo(
    nome_catalogo: str, conn: sqlite3.Connection = Depends(get_db)
) -> List[Dict[str, Any]]:
    """Retorna os itens internos de um catálogo específico."""
    try:
        return catalogo_service.obter_itens_catalogo(conn, nome_catalogo)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/{nome_catalogo}", response_model=MensagemResponse)
def salvar_itens_catalogo(
    nome_catalogo: str,
    itens: List[ItemCatalogo],
    conn: sqlite3.Connection = Depends(get_db),
) -> MensagemResponse:
    """Salva ou atualiza a lista de itens de um catálogo no SQLite."""
    try:
        catalogo_service.salvar_itens_catalogo(conn, nome_catalogo, itens)
        return MensagemResponse(mensagem="Catálogo salvo com sucesso!")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.delete("/{nome_catalogo}", response_model=MensagemResponse)
def deletar_catalogo_inteiro(
    nome_catalogo: str, conn: sqlite3.Connection = Depends(get_db)
) -> MensagemResponse:
    """Remove um catálogo inteiro do banco de dados."""
    try:
        catalogo_service.deletar_catalogo(conn, nome_catalogo)
        return MensagemResponse(mensagem=f"Catálogo {nome_catalogo} removido.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
