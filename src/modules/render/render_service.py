"""Orquestração da renderização 3D server-side (Blender Eevee, modelo stateless).

Desacoplado do motor de layout: recebe os itens já calculados pelo front-end
e apenas converte as coordenadas para o job do Blender (SPEC_3D_RENDER.md).
"""

import os
import uuid
from typing import Any, Dict

from core.config import DIRETORIO_TEMPORARIO
from engine.blender_headless import (
    CAMINHO_TEMPLATE_PADRAO,
    DIRETORIO_GLB_PADRAO,
    blender_disponivel,
    montar_job_render,
    obter_executavel_blender,
    renderizar_cena_3d,
)
from modules.pipeline.pipeline_service import normalizar_slug_cliente

from .render_schema import Render3DRequest


def obter_status_render() -> Dict[str, Any]:
    """Diagnóstico do ambiente: Blender, template de cenário e diretório de GLBs."""
    disponivel = blender_disponivel()
    return {
        "status": "ok",
        "blender_disponivel": disponivel,
        "blender_executavel": obter_executavel_blender(),
        "template_cenario": CAMINHO_TEMPLATE_PADRAO,
        "template_disponivel": os.path.exists(CAMINHO_TEMPLATE_PADRAO),
        "diretorio_glb": DIRETORIO_GLB_PADRAO,
        "pronto_para_renderizar": disponivel,
    }


def renderizar_png(dados: Render3DRequest) -> str:
    """Renderiza a cena 3D em Eevee a partir dos itens recebidos (stateless).

    NÃO recalcula a geometria: apenas converte as coordenadas do layout
    (cm, canto) para o espaço 3D (metros, centro) e dispara o Blender.

    Retorna o caminho do PNG gerado.

    Levanta:
        BlenderNaoEncontradoError: Blender indisponível (HTTP 503).
        FalhaRenderizacaoBlenderError: falha na renderização (HTTP 500).
    """
    nome_slug = normalizar_slug_cliente(dados.nome_cliente)
    caminho_png = os.path.join(
        DIRETORIO_TEMPORARIO, f"render3d_{nome_slug}_{uuid.uuid4().hex[:8]}.png"
    )

    itens_layout = [item.model_dump(mode="json") for item in dados.itens]

    job = montar_job_render(
        itens_layout,
        largura_balcao_cm=dados.largura_balcao_cm,
        profundidade_balcao_cm=dados.profundidade_balcao_cm,
        caminho_saida_png=caminho_png,
        altura_balcao_cm=dados.altura_balcao_cm,
        exibir_cotas=dados.exibir_cotas,
        modulos_balcao_cm=dados.modulos_balcao_cm,
    )
    return renderizar_cena_3d(job)
