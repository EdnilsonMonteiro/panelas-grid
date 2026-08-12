"""Contratos do pipeline de layout (seções e configuração do balcão)."""

from typing import Any, Dict, List, Literal

from pydantic import BaseModel, Field


class ConfiguracaoBalcao(BaseModel):
    """Dimensões do balcão informadas pela UI."""

    L: float = Field(gt=0, description="Comprimento do balcão em cm")
    P: float = Field(gt=0, description="Profundidade do balcão em cm")
    espaco: float = Field(default=0.5, ge=0, description="Espaçamento entre peças em cm")


class SecaoPipeline(BaseModel):
    """Instância de uma seção do pipeline de montagem do layout."""

    tipo: str = Field(min_length=1, description="Classe da seção (ver /api/schemas)")
    nome: str = Field(min_length=1)
    pct_largura_alvo: float = Field(default=1.0, gt=0, le=1)
    pista: Literal["fria", "quente"] = Field(
        default="quente", description="Pista fria ou quente desta seção"
    )
    parametros: Dict[str, Any] = Field(default_factory=dict)


class ProcessarLayoutRequest(BaseModel):
    """Payload de processamento de layout (prévia PDF/PPTX)."""

    nome_cliente: str = Field(default="Cliente Não Informado")
    configuracao_balcao: ConfiguracaoBalcao
    pipeline_secoes: List[SecaoPipeline] = Field(min_length=1)


class ItemLayout(BaseModel):
    """Travessa alocada pelo motor geométrico.

    Coordenadas (x, y) do CANTO superior-esquerdo da peça, em centímetros,
    conforme produzido pelo LayoutEngine (SPEC_3D_RENDER.md, modelo stateless).
    """

    nome: str = Field(min_length=1)
    formato: Literal["circulo", "retangulo"] = "retangulo"
    x: float = Field(ge=0)
    y: float = Field(ge=0)
    w: float = Field(gt=0, description="Largura ocupada em cm")
    h: float = Field(gt=0, description="Profundidade ocupada em cm")


class ProcessarV1Response(BaseModel):
    """Resposta do POST /api/v1/buffet/processar (modelo stateless).

    Devolve o PDF (base64) para prévia imediata e, principalmente, a lista
    de itens alocados + dimensões do balcão para o front-end reutilizar no
    POST /api/v1/buffet/render-3d sem reprocessar a geometria.
    """

    pdf_base64: str
    nome_arquivo_pdf: str
    nome_slug: str = Field(description="Slug do cliente (usado em /api/download-pptx)")
    largura_balcao_cm: float
    profundidade_balcao_cm: float
    itens: List[ItemLayout]
