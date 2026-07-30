"""Rotas do pipeline de layout (/api/schemas, /api/processar, /api/v1/buffet/processar)."""

from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from modules.pipeline import pipeline_service
from modules.pipeline.pipeline_schema import (
    ItemLayout,
    ProcessarLayoutRequest,
    ProcessarV1Response,
)

router = APIRouter(prefix="/api", tags=["pipeline"])

# Namespace versionado do buffet (modelo stateless, SPEC_3D_RENDER.md)
router_v1 = APIRouter(prefix="/api/v1/buffet", tags=["pipeline-v1"])


@router.get("/schemas", response_model=List[Dict[str, Any]])
def obter_schemas_secoes() -> List[Dict[str, Any]]:
    """Retorna o UI_SCHEMA de cada seção registrada, para a UI montar os cards."""
    return pipeline_service.obter_schemas_secoes()


@router.post("/processar")
def processar_pipeline(dados: ProcessarLayoutRequest) -> FileResponse:
    """Calcula o layout, gera PDF + PPTX e devolve o PDF para prévia imediata."""
    try:
        caminho_pdf, _, nome_slug, _ = pipeline_service.processar_layout_e_exportar(
            dados
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Erro no processamento: {e}"
        ) from e

    return FileResponse(
        caminho_pdf,
        media_type="application/pdf",
        filename=f"layout_{nome_slug}.pdf",
        content_disposition_type="inline",
    )


@router_v1.post("/processar", response_model=ProcessarV1Response)
def processar_pipeline_v1(dados: ProcessarLayoutRequest) -> ProcessarV1Response:
    """Calcula o layout 2D e devolve PDF (base64) + itens alocados + dimensões.

    Os itens retornados devem ser enviados pelo front-end ao endpoint
    POST /api/v1/buffet/render-3d, sem reprocessar a geometria (stateless).
    """
    try:
        caminho_pdf, _, nome_slug, pedido = (
            pipeline_service.processar_layout_e_exportar(dados)
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Erro no processamento: {e}"
        ) from e

    modulo = pedido.modulos[0]

    return ProcessarV1Response(
        pdf_base64=pipeline_service.ler_arquivo_base64(caminho_pdf),
        nome_arquivo_pdf=f"layout_{nome_slug}.pdf",
        nome_slug=nome_slug,
        largura_balcao_cm=modulo.engine.L,
        profundidade_balcao_cm=modulo.engine.P,
        itens=[ItemLayout(**item) for item in modulo.engine.itens],
    )
