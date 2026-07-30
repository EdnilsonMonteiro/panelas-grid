"""Rotas de exportação de arquivos gerados (/api/download-pptx)."""

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from modules.pipeline import pipeline_service

MIMETYPE_PPTX = (
    "application/vnd.openxmlformats-officedocument.presentationml.presentation"
)

router = APIRouter(prefix="/api", tags=["exportacao"])


@router.get("/download-pptx/{nome_slug}")
def baixar_pptx(nome_slug: str) -> FileResponse:
    """Recupera o PPTX já gerado anteriormente, sem reprocessar o motor geométrico."""
    caminho_pptx = pipeline_service.localizar_pptx_pronto(nome_slug)
    if caminho_pptx is None:
        raise HTTPException(
            status_code=404,
            detail=(
                "O arquivo PPTX correspondente expirou ou não foi gerado. "
                "Processe o layout novamente."
            ),
        )

    return FileResponse(
        caminho_pptx,
        media_type=MIMETYPE_PPTX,
        filename=f"layout_{nome_slug}.pptx",
    )
