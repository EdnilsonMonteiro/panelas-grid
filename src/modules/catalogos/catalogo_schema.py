"""Contratos de catálogos de travessas/cubas."""

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class ItemCatalogo(BaseModel):
    """Item de um catálogo (cuba retangular ou panela redonda).

    `extra="allow"` preserva chaves adicionais consumidas pelo motor
    geométrico (ex.: "rotacionar", "largura", "altura").
    """

    model_config = ConfigDict(extra="allow")

    nome: str = Field(min_length=1)
    w: Optional[float] = Field(default=None, gt=0, description="Largura em cm")
    h: Optional[float] = Field(default=None, gt=0, description="Profundidade em cm")
    rot: bool = Field(default=False, description="Permite rotação de 90°")
    diametro: Optional[float] = Field(
        default=None, gt=0, description="Diâmetro em cm (panelas redondas)"
    )
