"""Coleta, consolidação e persistência de métricas de performance da renderização.

Chaveado pela variável de ambiente ENABLE_RENDER_METRICS (true/1/yes,
case-insensitive). Quando inativa, este módulo não executa timers nem cria
arquivos: o fluxo padrão de renderização permanece silencioso e sem overhead.

O relatório final é salvo em `assets/reports/metrics_YYYYMMDD_HHMMSS.json`
e os valores simplificados são injetados nos headers HTTP da resposta
(ex.: X-Render-Time-Sec).
"""

import json
import os
import platform
import time
from typing import Any, Dict, Optional

from core.config import DIRETORIO_REPORTS, env_habilitada

ENABLE_RENDER_METRICS = "ENABLE_RENDER_METRICS"

# Chaves de duração (segundos) reportadas pelo script interno do Blender
CHAVES_TEMPO_BLENDER = (
    "init_sec",
    "balcao_setup_sec",
    "food_allocation_sec",
    "boolean_operations_sec",
    "environment_and_dimensions_sec",
    "eevee_render_sec",
    "file_save_sec",
    "total_script_sec",
)


def metricas_render_ativas() -> bool:
    """True quando ENABLE_RENDER_METRICS é true/1/yes (case-insensitive)."""
    return env_habilitada(ENABLE_RENDER_METRICS)


def _arredondar(valor: Optional[float]) -> Optional[float]:
    """Arredonda para 6 casas; preserva None (métrica não disponível)."""
    if valor is None:
        return None
    return round(float(valor), 6)


# ---------------------------------------------------------------------------
# Ambiente do servidor (processo FastAPI)
# ---------------------------------------------------------------------------
def _ram_total_gb() -> float:
    """Memória RAM total da máquina em GB (best-effort, sem hard dependency)."""
    try:
        import psutil

        return round(psutil.virtual_memory().total / (1024.0 ** 3), 2)
    except Exception:
        pass
    try:
        if hasattr(os, "sysconf"):
            paginas = os.sysconf("SC_PHYS_PAGES")
            tamanho = os.sysconf("SC_PAGE_SIZE")
            return round(paginas * tamanho / (1024.0 ** 3), 2)
    except Exception:
        pass
    return 0.0


def coletar_ambiente() -> Dict[str, Any]:
    """Descreve a máquina do servidor (sistema, CPU, RAM)."""
    processador = platform.processor() or platform.machine() or "desconhecido"
    return {
        "os": f"{platform.system()} ({platform.machine()})",
        "processor": processador,
        "cpu_count": os.cpu_count() or 1,
        "ram_total_gb": _ram_total_gb(),
        "blender_version": None,
        "render_engine": None,
    }


def _coletar_job_info(dados, job: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Resume o job enviado ao Blender (contagens e resolução)."""
    itens = list(getattr(dados, "itens", []) or [])
    render = (job or {}).get("render", {})
    return {
        "items_count": len(itens),
        "circular_items_count": sum(
            1 for item in itens if getattr(item, "formato", "") == "circulo"
        ),
        "rectangular_items_count": sum(
            1 for item in itens if getattr(item, "formato", "") != "circulo"
        ),
        "output_resolution": [
            int(render.get("resolucao_x", 1280)),
            int(render.get("resolucao_y", 960)),
        ],
    }


def construir_relatorio_render(
    dados,
    job: Dict[str, Any],
    coletor: Dict[str, Any],
    total_latency_sec: Optional[float] = None,
) -> Dict[str, Any]:
    """Consolida o relatório final conforme assets/reports/metrics_*.json.

    `coletor` reúne as métricas medidas pelo processo FastAPI
    (json_build_sec, subprocess_total_sec, subprocess_overhead_sec) e o JSON
    cru reportado pelo script do Blender (blender_interno).
    """
    interno = coletor.get("blender_interno") or {}

    ambiente = coletar_ambiente()
    ambiente["blender_version"] = interno.get("blender_version")
    ambiente["render_engine"] = interno.get("render_engine") or (
        (job or {}).get("render", {}).get("motor")
    )
    # Dispositivo de render reportado pelo script do Blender (ex.: 'NVIDIA
    # Corporation | NVIDIA GeForce RTX 4060 Ti'). Ausente quando a telemetria
    # está inativa ou o gpu.init() falhou. Em servidor sem GPU, acusará o
    # software rasterizer (llvmpipe/WARP), provando que o render não usou GPU.
    ambiente["render_device"] = interno.get("render_device")

    return {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "environment": ambiente,
        "job_info": _coletar_job_info(dados, job),
        "metrics": {
            "fastapi_pipeline": {
                "json_build_sec": _arredondar(coletor.get("json_build_sec")),
                "subprocess_total_sec": _arredondar(
                    coletor.get("subprocess_total_sec")
                ),
                "subprocess_overhead_sec": _arredondar(
                    coletor.get("subprocess_overhead_sec")
                ),
                "total_latency_sec": _arredondar(total_latency_sec),
            },
            "blender_internal": {
                chave: _arredondar(interno.get(chave))
                for chave in CHAVES_TEMPO_BLENDER
            },
        },
        "resource_usage": {
            "peak_memory_mb": round(float(interno.get("peak_memory_mb", 0.0)), 1),
            "cpu_percent": round(float(interno.get("cpu_percent", 0.0)), 1),
        },
    }


def salvar_relatorio(relatorio: Dict[str, Any]) -> str:
    """Grava o relatório em assets/reports/metrics_YYYYMMDD_HHMMSS.json.

    O diretório é criado caso não exista. Retorna o caminho do arquivo.
    """
    os.makedirs(DIRETORIO_REPORTS, exist_ok=True)
    nome = f"metrics_{time.strftime('%Y%m%d_%H%M%S')}.json"
    caminho = os.path.join(DIRETORIO_REPORTS, nome)
    with open(caminho, "w", encoding="utf-8") as arquivo:
        json.dump(relatorio, arquivo, ensure_ascii=False, indent=2)
    return caminho


def headers_metricas(relatorio: Dict[str, Any]) -> Dict[str, str]:
    """Simplifica as métricas principais para os headers da resposta HTTP."""
    pipeline = relatorio.get("metrics", {}).get("fastapi_pipeline", {})
    headers = {}
    total = pipeline.get("total_latency_sec")
    if total is not None:
        headers["X-Render-Time-Sec"] = f"{total:.2f}"
    sub = pipeline.get("subprocess_total_sec")
    if sub is not None:
        headers["X-Render-Blender-Sec"] = f"{sub:.2f}"
    overhead = pipeline.get("subprocess_overhead_sec")
    if overhead is not None:
        headers["X-Render-Subprocess-Overhead-Sec"] = f"{overhead:.2f}"
    return headers
