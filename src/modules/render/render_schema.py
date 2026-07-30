"""Contratos da renderização 3D server-side (Blender Eevee, modelo stateless)."""

from typing import List

from modules.pipeline.pipeline_schema import ItemLayout
from pydantic import BaseModel, Field


class Render3DRequest(BaseModel):
    """Payload stateless do POST /api/v1/buffet/render-3d.

    Recebe diretamente as dimensões do balcão e a lista de itens JÁ calculada
    (pelo POST /api/v1/buffet/processar), sem reprocessar a geometria.
    """

    nome_cliente: str = Field(default="Cliente Não Informado")
    largura_balcao_cm: float = Field(gt=0)
    profundidade_balcao_cm: float = Field(gt=0)
    altura_balcao_cm: float = Field(default=90.0, gt=0)
    itens: List[ItemLayout] = Field(min_length=1)


class Render3DStatusResponse(BaseModel):
    """Diagnóstico do ambiente de renderização do servidor."""

    status: str
    blender_disponivel: bool
    blender_executavel: str
    template_cenario: str
    template_disponivel: bool
    diretorio_glb: str
    pronto_para_renderizar: bool
