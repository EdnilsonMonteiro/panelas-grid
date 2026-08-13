"""Regras de negócio do processamento de layout e exportação (PDF/PPTX)."""

import base64
import os
import unicodedata
from typing import Any, Dict, List, Optional, Tuple

from core.config import DIRETORIO_TEMPORARIO
from modelos import ComposicaoBalcao
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


GAP_PLACAS_CM = 1.0


def combinar_modulos_composicao(composicao):
    """Combina os itens de todos os módulos (placas) lado a lado.

    Retorna (itens_combinados, largura_total_cm, profundidade_cm,
    larguras_por_placa_cm). Cada placa tem seus itens deslocados no eixo X
    pela soma das larguras anteriores + gap, para o render 3D das placas juntas.
    """
    itens = []
    larguras_placas = []
    x_deslocamento = 0.0
    profundidade = 0.0
    for modulo in composicao.modulos:
        larguras_placas.append(modulo.engine.L)
        profundidade = max(profundidade, modulo.engine.P)
        for item in modulo.engine.itens:
            copia = dict(item)
            copia["x"] = round(item["x"] + x_deslocamento, 2)
            itens.append(copia)
        x_deslocamento += modulo.engine.L + GAP_PLACAS_CM
    largura_total = x_deslocamento - GAP_PLACAS_CM
    return itens, largura_total, profundidade, larguras_placas


def calcular_layout(dados: ProcessarLayoutRequest) -> ComposicaoBalcao:
    """Executa o motor geométrico e devolve a composição com os módulos calculados."""
    nome_cliente = dados.nome_cliente.strip() or "Cliente Não Informado"
    composicao = ComposicaoBalcao(nome_cliente=nome_cliente)
    return construir_pipeline_desde_json(dados.model_dump(mode="json"), composicao)


def processar_layout_e_exportar(
    dados: ProcessarLayoutRequest,
) -> Tuple[str, str, str, ComposicaoBalcao]:
    """Calcula o layout e gera PDF + PPTX no diretório temporário.

    Retorna (caminho_pdf, caminho_pptx, nome_slug, composicao_calculada).
    A composição devolvida permite inspecionar os itens alocados pelo motor
    (modelo stateless: o front-end os reutiliza na renderização 3D).
    """
    composicao = calcular_layout(dados)
    nome_slug = normalizar_slug_cliente(dados.nome_cliente)

    caminho_pdf = os.path.join(DIRETORIO_TEMPORARIO, f"layout_{nome_slug}.pdf")
    caminho_pptx = os.path.join(DIRETORIO_TEMPORARIO, f"layout_{nome_slug}.pptx")

    ExportadorPDF.gerar_layout(composicao, caminho_pdf)
    ExportadorPPTX.gerar_layout(composicao, caminho_pptx)

    return caminho_pdf, caminho_pptx, nome_slug, composicao


def ler_arquivo_base64(caminho: str) -> str:
    """Lê um arquivo binário e devolve seu conteúdo codificado em base64."""
    with open(caminho, "rb") as arquivo:
        return base64.b64encode(arquivo.read()).decode("ascii")


def localizar_pptx_pronto(nome_slug: str) -> Optional[str]:
    """Localiza o PPTX previamente gerado, se ainda existir no diretório temporário."""
    caminho_pptx = os.path.join(DIRETORIO_TEMPORARIO, f"layout_{nome_slug}.pptx")
    return caminho_pptx if os.path.exists(caminho_pptx) else None
