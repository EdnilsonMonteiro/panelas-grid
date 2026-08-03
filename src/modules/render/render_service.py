"""Orquestração da renderização 3D server-side (Blender Eevee, modelo stateless).

Desacoplado do motor de layout: recebe os itens já calculados pelo front-end
e apenas converte as coordenadas para o job do Blender (SPEC_3D_RENDER.md).
Quando ENABLE_RENDER_METRICS está ativo, coleta a telemetria ponta a ponta
e devolve o relatório consolidado junto ao caminho do PNG.
"""

import os
import time
import uuid
from typing import Any, Dict, Optional, Tuple

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

from .render_metrics import (
    construir_relatorio_render,
    metricas_render_ativas,
)
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


def renderizar_png(dados: Render3DRequest) -> Tuple[str, Optional[Dict[str, Any]]]:
    """Renderiza a cena 3D em Eevee a partir dos itens recebidos (stateless).

    NÃO recalcula a geometria: apenas converte as coordenadas do layout
    (cm, canto) para o espaço 3D (metros, centro) e dispara o Blender.

    Retorna (caminho_do_png, relatorio_de_metricas). O relatório é None quando
    ENABLE_RENDER_METRICS está inativo (fluxo padrão, sem telemetria).

    Levanta:
        BlenderNaoEncontradoError: Blender indisponível (HTTP 503).
        FalhaRenderizacaoBlenderError: falha na renderização (HTTP 500).
    """
    nome_slug = normalizar_slug_cliente(dados.nome_cliente)
    caminho_png = os.path.join(
        DIRETORIO_TEMPORARIO, f"render3d_{nome_slug}_{uuid.uuid4().hex[:8]}.png"
    )

    itens_layout = [item.model_dump(mode="json") for item in dados.itens]

    coletor: Optional[Dict[str, Any]] = {} if metricas_render_ativas() else None
    inicio_montagem = time.perf_counter() if coletor is not None else None

    job = montar_job_render(
        itens_layout,
        largura_balcao_cm=dados.largura_balcao_cm,
        profundidade_balcao_cm=dados.profundidade_balcao_cm,
        caminho_saida_png=caminho_png,
        altura_balcao_cm=dados.altura_balcao_cm,
        exibir_cotas=dados.exibir_cotas,
        modulos_balcao_cm=dados.modulos_balcao_cm,
    )
    if coletor is not None:
        coletor["json_build_sec"] = time.perf_counter() - inicio_montagem

    caminho_png = renderizar_cena_3d(job, coletor_metricas=coletor)

    if coletor is not None:
        relatorio = construir_relatorio_render(
            dados, job, coletor, total_latency_sec=None
        )
        return caminho_png, relatorio
    return caminho_png, None
