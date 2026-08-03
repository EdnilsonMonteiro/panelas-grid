"""Rotas da renderização 3D server-side (/api/v1/buffet/render-3d, stateless)."""

import os
import time

from engine.blender_headless import (
    BlenderNaoEncontradoError,
    FalhaRenderizacaoBlenderError,
)
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from modules.pipeline.pipeline_service import normalizar_slug_cliente
from starlette.background import BackgroundTask

from . import render_service
from .render_metrics import headers_metricas, salvar_relatorio
from .render_schema import Render3DRequest, Render3DStatusResponse

router = APIRouter(prefix="/api/v1/buffet", tags=["render-3d"])


@router.get("/render-3d/status", response_model=Render3DStatusResponse)
def status_render_3d() -> Render3DStatusResponse:
    """Diagnóstico do ambiente: Blender, template de cenário e diretório de GLBs."""
    return Render3DStatusResponse(**render_service.obter_status_render())


@router.post("/render-3d")
def renderizar_3d(payload: Render3DRequest) -> FileResponse:
    """Renderiza a cena 3D em Eevee a partir dos itens recebidos (sem recalcular a geometria)."""
    t_chegada = time.perf_counter()
    try:
        caminho_png, relatorio = render_service.renderizar_png(payload)
    except BlenderNaoEncontradoError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except FalhaRenderizacaoBlenderError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Erro ao renderizar a cena 3D: {e}"
        ) from e

    headers = {}
    if relatorio is not None:
        relatorio["metrics"]["fastapi_pipeline"]["total_latency_sec"] = round(
            time.perf_counter() - t_chegada, 6
        )
        caminho_relatorio = salvar_relatorio(relatorio)
        print(f" > [Métricas] Relatório salvo em {caminho_relatorio}")
        headers = headers_metricas(relatorio)

    nome_slug = normalizar_slug_cliente(payload.nome_cliente)
    return FileResponse(
        caminho_png,
        media_type="image/png",
        filename=f"render3d_{nome_slug}.png",
        headers=headers,
        background=BackgroundTask(os.unlink, caminho_png),
    )
