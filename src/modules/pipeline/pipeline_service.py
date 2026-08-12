"""Regras de negócio do processamento de layout e exportação (PDF/PPTX)."""

import base64
import os
import unicodedata
from typing import Any, Dict, List, Optional, Tuple

from core.config import DIRETORIO_TEMPORARIO
from modelos import PedidoCliente
from modules.exportacao.exportadores.pdf import ExportadorPDF
from modules.exportacao.exportadores.pptx import ExportadorPPTX
from modules.pipeline.pipeline_schema import ProcessarLayoutRequest
from pipeline_builder import REGISTRO_SECOES, construir_pipeline_desde_json


def normalizar_slug_cliente(nome_cliente: str) -> str:
    """Gera o slug do nome do cliente (minúsculas, underscores, sem acentos).

    Também remove/substitui caracteres inválidos em nomes de arquivo
    (ex.: '/', ':', '*' etc.), garantindo que o slug possa ser usado
    tanto em caminhos do disco quanto em nomes de download.
    """
    slug = nome_cliente.strip().replace(" ", "_").lower() or "cliente_nao_informado"
    slug = "".join(
        c for c in unicodedata.normalize("NFD", slug) if unicodedata.category(c) != "Mn"
    )
    # Caracteres proibidos em nomes de arquivo no Windows / URLs de download
    for caractere in '/\\:*?"<>|':
        slug = slug.replace(caractere, "_")
    slug = "_".join(parte for parte in slug.split("_") if parte)
    return slug or "cliente_nao_informado"


def obter_schemas_secoes() -> List[Dict[str, Any]]:
    """Extrai dinamicamente o UI_SCHEMA de cada seção registrada."""
    return [
        classe.UI_SCHEMA
        for classe in REGISTRO_SECOES.values()
        if hasattr(classe, "UI_SCHEMA")
    ]


def calcular_layout(dados: ProcessarLayoutRequest) -> PedidoCliente:
    """Executa o motor geométrico e devolve o pedido com os módulos calculados."""
    nome_cliente = dados.nome_cliente.strip() or "Cliente Não Informado"
    pedido = PedidoCliente(nome_cliente=nome_cliente)
    return construir_pipeline_desde_json(dados.model_dump(mode="json"), pedido)


def processar_layout_e_exportar(
    dados: ProcessarLayoutRequest,
) -> Tuple[str, str, str, PedidoCliente]:
    """Calcula o layout e gera PDF + PPTX no diretório temporário.

    Retorna (caminho_pdf, caminho_pptx, nome_slug, pedido_calculado).
    O pedido devolvido permite inspecionar os itens alocados pelo motor
    (modelo stateless: o front-end os reutiliza na renderização 3D).
    """
    pedido = calcular_layout(dados)
    nome_slug = normalizar_slug_cliente(dados.nome_cliente)

    caminho_pdf = os.path.join(DIRETORIO_TEMPORARIO, f"layout_{nome_slug}.pdf")
    caminho_pptx = os.path.join(DIRETORIO_TEMPORARIO, f"layout_{nome_slug}.pptx")

    ExportadorPDF.gerar_layout(pedido, caminho_pdf)
    ExportadorPPTX.gerar_layout(pedido, caminho_pptx)

    return caminho_pdf, caminho_pptx, nome_slug, pedido


def ler_arquivo_base64(caminho: str) -> str:
    """Lê um arquivo binário e devolve seu conteúdo codificado em base64."""
    with open(caminho, "rb") as arquivo:
        return base64.b64encode(arquivo.read()).decode("ascii")


def localizar_pptx_pronto(nome_slug: str) -> Optional[str]:
    """Localiza o PPTX previamente gerado, se ainda existir no diretório temporário."""
    caminho_pptx = os.path.join(DIRETORIO_TEMPORARIO, f"layout_{nome_slug}.pptx")
    return caminho_pptx if os.path.exists(caminho_pptx) else None
