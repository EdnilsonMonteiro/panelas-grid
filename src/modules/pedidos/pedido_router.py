"""Rotas de pedidos do cliente (/api/pedidos) e exportação de opções."""

import sqlite3
from typing import List, Optional

from core.dependencies import get_db
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from modules.pedidos.pedido_schema import (
    LayoutPedidoEntrada,
    LayoutPedidoResposta,
    PedidoAtualizarEntrada,
    PedidoEntrada,
    PedidoListaResposta,
    PedidoResposta,
    ReordenarLayoutsEntrada,
)
from modules.pipeline import pipeline_service
from modules.shared.schemas.comum import MensagemResponse

from . import pedido_service

MIMETYPE_PPTX = (
    "application/vnd.openxmlformats-officedocument.presentationml.presentation"
)

router = APIRouter(prefix="/api/pedidos", tags=["pedidos"])


@router.get("", response_model=List[PedidoListaResposta])
def listar_pedidos(
    limite: Optional[int] = Query(default=None, ge=1),
    busca: Optional[str] = Query(default=None),
    conn: sqlite3.Connection = Depends(get_db),
) -> List[PedidoListaResposta]:
    """Retorna os pedidos (mais recentes primeiro).

    `?limite=3` retorna apenas os 3 recentes (sidebar) e `?busca=termo`
    filtra por nome do pedido ou cliente (ferramenta de busca).
    """
    try:
        return pedido_service.listar_pedidos(conn, limite=limite, busca=busca)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("", response_model=PedidoResposta, status_code=201)
def criar_pedido(
    dados: PedidoEntrada, conn: sqlite3.Connection = Depends(get_db)
) -> PedidoResposta:
    """Cria um novo pedido do cliente."""
    try:
        return pedido_service.criar_pedido(conn, dados)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/{pedido_id}", response_model=PedidoResposta)
def obter_pedido(
    pedido_id: int, conn: sqlite3.Connection = Depends(get_db)
) -> PedidoResposta:
    """Retorna um pedido com seus layouts (opções)."""
    try:
        pedido = pedido_service.obter_pedido(conn, pedido_id)
        if pedido is None:
            raise HTTPException(status_code=404, detail="Pedido não encontrado.")
        return pedido
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.put("/{pedido_id}", response_model=PedidoResposta)
def atualizar_pedido(
    pedido_id: int,
    dados: PedidoAtualizarEntrada,
    conn: sqlite3.Connection = Depends(get_db),
) -> PedidoResposta:
    """Atualiza nome/cliente do pedido (mantém cabeçalho do export em sincronia)."""
    try:
        pedido = pedido_service.atualizar_pedido(conn, pedido_id, dados)
        if pedido is None:
            raise HTTPException(status_code=404, detail="Pedido não encontrado.")
        return pedido
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.delete("/{pedido_id}", response_model=MensagemResponse)
def deletar_pedido(
    pedido_id: int, conn: sqlite3.Connection = Depends(get_db)
) -> MensagemResponse:
    """Remove um pedido e todas as suas opções (layouts)."""
    try:
        pedido_service.deletar_pedido(conn, pedido_id)
        return MensagemResponse(mensagem="Pedido removido com sucesso!")
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/{pedido_id}/layouts", response_model=LayoutPedidoResposta, status_code=201)
def salvar_layout(
    pedido_id: int,
    dados: LayoutPedidoEntrada,
    conn: sqlite3.Connection = Depends(get_db),
) -> LayoutPedidoResposta:
    """Persiste o layout atual como uma nova opção do pedido."""
    try:
        return pedido_service.salvar_layout(conn, pedido_id, dados)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.put("/{pedido_id}/layouts/reordenar", response_model=MensagemResponse)
def reordenar_layouts(
    pedido_id: int,
    dados: ReordenarLayoutsEntrada,
    conn: sqlite3.Connection = Depends(get_db),
) -> MensagemResponse:
    """Reatribui a ordem das opções do pedido."""
    try:
        if pedido_service.obter_pedido(conn, pedido_id) is None:
            raise HTTPException(status_code=404, detail="Pedido não encontrado.")
        pedido_service.reordenar_layouts(conn, pedido_id, dados.ordered_layout_ids)
        return MensagemResponse(mensagem="Ordem das opções atualizada com sucesso!")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.delete("/layouts/{layout_id}", response_model=MensagemResponse)
def deletar_layout(
    layout_id: int, conn: sqlite3.Connection = Depends(get_db)
) -> MensagemResponse:
    """Remove uma opção do pedido e renumera as demais."""
    try:
        pedido_service.deletar_layout(conn, layout_id)
        return MensagemResponse(mensagem="Opção removida com sucesso!")
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/{pedido_id}/exportar/pdf")
def exportar_pdf(
    pedido_id: int, conn: sqlite3.Connection = Depends(get_db)
) -> FileResponse:
    """Gera o PDF com uma página por opção salva do pedido."""
    try:
        pedido = pedido_service.obter_pedido(conn, pedido_id)
        if pedido is None:
            raise HTTPException(status_code=404, detail="Pedido não encontrado.")
        caminho_pdf = pedido_service.exportar_pdf(conn, pedido_id)
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro na exportação: {e}") from e

    return FileResponse(
        caminho_pdf,
        media_type="application/pdf",
        filename=f"layout_{pipeline_service.normalizar_slug_cliente(pedido.nome_pedido)}_opcoes.pdf",
        content_disposition_type="inline",
    )


@router.get("/{pedido_id}/exportar/pptx")
def exportar_pptx(
    pedido_id: int, conn: sqlite3.Connection = Depends(get_db)
) -> FileResponse:
    """Gera o PPTX com um slide por opção salva do pedido."""
    try:
        pedido = pedido_service.obter_pedido(conn, pedido_id)
        if pedido is None:
            raise HTTPException(status_code=404, detail="Pedido não encontrado.")
        caminho_pptx = pedido_service.exportar_pptx(conn, pedido_id)
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro na exportação: {e}") from e

    return FileResponse(
        caminho_pptx,
        media_type=MIMETYPE_PPTX,
        filename=f"layout_{pipeline_service.normalizar_slug_cliente(pedido.nome_pedido)}_opcoes.pptx",
    )
