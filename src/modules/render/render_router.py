"""Rotas da renderização 3D server-side (/api/v1/buffet/render-3d, stateless)."""

import os

from engine.blender_headless import (
    BlenderNaoEncontradoError,
    FalhaRenderizacaoBlenderError,
)
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from modules.pipeline.pipeline_service import normalizar_slug_cliente
from starlette.background import BackgroundTask

from . import render_service
from .render_schema import Render3DRequest, Render3DStatusResponse

router = APIRouter(prefix="/api/v1/buffet", tags=["render-3d"])


@router.get("/render-3d/status", response_model=Render3DStatusResponse)
def status_render_3d() -> Render3DStatusResponse:
    """Diagnóstico do ambiente: Blender, template de cenário e diretório de GLBs."""
    return Render3DStatusResponse(**render_service.obter_status_render())


@router.post("/render-3d")
def renderizar_3d(payload: Render3DRequest) -> FileResponse:
    """Renderiza a cena 3D em Eevee a partir dos itens recebidos (sem recalcular a geometria)."""
    try:
        caminho_png = render_service.renderizar_png(payload)
    except BlenderNaoEncontradoError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except FalhaRenderizacaoBlenderError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Erro ao renderizar a cena 3D: {e}"
        ) from e

    nome_slug = normalizar_slug_cliente(payload.nome_cliente)
    return FileResponse(
        caminho_png,
        media_type="image/png",
        filename=f"render3d_{nome_slug}.png",
        background=BackgroundTask(os.unlink, caminho_png),
    )
