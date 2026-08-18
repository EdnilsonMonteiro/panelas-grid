"""Regras de negócio de pedidos do cliente e seus layouts (opções)."""

import json
import os
import sqlite3
from datetime import datetime
from typing import Any, Dict, List, Optional

from PIL import Image

from core.config import DIRETORIO_TEMPORARIO
from modelos import ComposicaoBalcao
from modules.exportacao.exportadores.pdf import ExportadorPDF
from modules.exportacao.exportadores.pptx import ExportadorPPTX
from modules.exportacao.exportadores.proposta import ExportadorProposta
from modules.pedidos.pedido_schema import (
    LayoutPedidoEntrada,
    LayoutPedidoResposta,
    PedidoAtualizarEntrada,
    PedidoEntrada,
    PedidoListaResposta,
    PedidoResposta,
)
from modules.pipeline.pipeline_service import (
    combinar_modulos_composicao,
    normalizar_slug_cliente,
)
from modules.render import render_service
from modules.render.render_schema import Render3DRequest
from pipeline_builder import construir_pipeline_desde_json

from . import pedido_repository as repo


def listar_pedidos(
    conn: sqlite3.Connection,
    limite: Optional[int] = None,
    busca: Optional[str] = None,
) -> List[PedidoListaResposta]:
    """Retorna os pedidos para alimentar a sidebar (recentes) e a busca."""
    return [
        PedidoListaResposta(
            id=str(linha["id"]),
            nome_pedido=linha["nome_pedido"],
            nome_cliente=linha["nome_cliente"],
            qtd_layouts=int(linha["qtd_layouts"]),
        )
        for linha in repo.listar_pedidos(conn, limite=limite, busca=busca)
    ]


def criar_pedido(conn: sqlite3.Connection, dados: PedidoEntrada) -> PedidoResposta:
    """Cria um novo pedido e devolve-o já com a lista (vazia) de layouts.

    Quando o nome do pedido não é informado, usa um timestamp legível como
    identificador (ex.: "12/08/2026 14:35:22").
    """
    nome_pedido = dados.nome_pedido or datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    pedido_id = repo.criar(conn, nome_pedido, dados.nome_cliente)
    return PedidoResposta(
        id=str(pedido_id),
        nome_pedido=nome_pedido,
        nome_cliente=dados.nome_cliente,
        layouts=[],
    )


def deletar_pedido(conn: sqlite3.Connection, pedido_id: int) -> None:
    """Remove um pedido e todos os seus layouts (opções)."""
    if repo.obter(conn, pedido_id) is None:
        raise ValueError("Pedido não encontrado.")
    repo.deletar_pedido(conn, pedido_id)


def atualizar_pedido(
    conn: sqlite3.Connection, pedido_id: int, dados: PedidoAtualizarEntrada
) -> Optional[PedidoResposta]:
    """Atualiza parcialmente um pedido (nome e/ou cliente) e devolve o pedido atualizado."""
    if repo.obter(conn, pedido_id) is None:
        return None

    if dados.nome_cliente is not None:
        repo.atualizar_nome_cliente(conn, pedido_id, dados.nome_cliente)
    if dados.nome_pedido is not None:
        repo.atualizar_nome_pedido(conn, pedido_id, dados.nome_pedido)

    return obter_pedido(conn, pedido_id)


def obter_pedido(conn: sqlite3.Connection, pedido_id: int) -> Optional[PedidoResposta]:
    """Retorna um pedido com seus layouts, ou None se não existir."""
    pedido = repo.obter(conn, pedido_id)
    if pedido is None:
        return None

    return PedidoResposta(
        id=str(pedido["id"]),
        nome_pedido=pedido["nome_pedido"],
        nome_cliente=pedido["nome_cliente"],
        layouts=[_mapear_layout(linha) for linha in repo.listar_layouts(conn, pedido_id)],
    )


def salvar_layout(
    conn: sqlite3.Connection, pedido_id: int, dados: LayoutPedidoEntrada
) -> LayoutPedidoResposta:
    """Persiste o layout atual como uma nova opção do pedido."""
    if repo.obter(conn, pedido_id) is None:
        raise ValueError("Pedido não encontrado.")

    opcao_numero = repo.proximo_numero_opcao(conn, pedido_id)

    config_json = json.dumps(
        dados.configuracao_balcao.model_dump(mode="json"), ensure_ascii=False
    )
    pipeline_json = json.dumps(
        [secao.model_dump(mode="json") for secao in dados.pipeline_secoes],
        ensure_ascii=False,
    )
    modulos_json = None
    if dados.modulos:
        modulos_json = json.dumps(
            [
                {
                    "configuracao_balcao": m.configuracao_balcao.model_dump(
                        mode="json"
                    ),
                    "pipeline_secoes": [
                        s.model_dump(mode="json") for s in m.pipeline_secoes
                    ],
                }
                for m in dados.modulos
            ],
            ensure_ascii=False,
        )

    novo_id = repo.inserir_layout(
        conn,
        pedido_id,
        opcao_numero,
        dados.titulo,
        config_json,
        pipeline_json,
        modulos_json=modulos_json,
    )

    return LayoutPedidoResposta(
        id=str(novo_id),
        opcao_numero=opcao_numero,
        titulo=dados.titulo,
        configuracao_balcao=json.loads(config_json),
        pipeline_secoes=json.loads(pipeline_json),
        modulos=json.loads(modulos_json) if modulos_json else [],
    )


def atualizar_layout(
    conn: sqlite3.Connection, layout_id: int, dados: LayoutPedidoEntrada
) -> LayoutPedidoResposta:
    """Atualiza o conteúdo de uma opção existente (edição)."""
    layout = repo.obter_layout(conn, layout_id)
    if layout is None:
        raise ValueError("Opção não encontrada.")

    config_json = json.dumps(
        dados.configuracao_balcao.model_dump(mode="json"), ensure_ascii=False
    )
    pipeline_json = json.dumps(
        [secao.model_dump(mode="json") for secao in dados.pipeline_secoes],
        ensure_ascii=False,
    )
    modulos_json = None
    if dados.modulos:
        modulos_json = json.dumps(
            [
                {
                    "configuracao_balcao": m.configuracao_balcao.model_dump(
                        mode="json"
                    ),
                    "pipeline_secoes": [
                        s.model_dump(mode="json") for s in m.pipeline_secoes
                    ],
                }
                for m in dados.modulos
            ],
            ensure_ascii=False,
        )

    repo.atualizar_layout(
        conn,
        layout_id,
        dados.titulo,
        config_json,
        pipeline_json,
        modulos_json=modulos_json,
    )

    return LayoutPedidoResposta(
        id=str(layout_id),
        opcao_numero=int(layout["opcao_numero"]),
        titulo=dados.titulo,
        configuracao_balcao=json.loads(config_json),
        pipeline_secoes=json.loads(pipeline_json),
        modulos=json.loads(modulos_json) if modulos_json else [],
    )


def deletar_layout(conn: sqlite3.Connection, layout_id: int) -> None:
    """Remove uma opção e renumera as demais sequencialmente (1..N)."""
    layout = repo.obter_layout(conn, layout_id)
    if layout is None:
        raise ValueError("Layout não encontrado.")

    repo.deletar_layout(conn, layout_id)
    repo.renumerar(conn, layout["pedido_id"])


def reordenar_layouts(
    conn: sqlite3.Connection, pedido_id: int, ordered_layout_ids: List[int]
) -> None:
    """Reatribui os números de opção na ordem final desejada."""
    repo.reordenar(conn, ordered_layout_ids)


def _reconstruir_composicoes(
    conn: sqlite3.Connection, pedido_id: int
) -> List[ComposicaoBalcao]:
    """Reconstrói as ComposicaoBalcao a partir das opções salvas (motor stateless)."""
    pedido = repo.obter(conn, pedido_id)
    if pedido is None:
        raise ValueError("Pedido não encontrado.")

    nome_cliente = pedido["nome_cliente"] or pedido["nome_pedido"]

    composicoes: List[ComposicaoBalcao] = []
    for linha in repo.listar_layouts(conn, pedido_id):
        composicao_calculada = ComposicaoBalcao(nome_cliente=nome_cliente)
        modulos = json.loads(linha["modulos_json"]) if linha.get("modulos_json") else []
        if modulos:
            payload = {"modulos": modulos}
        else:
            payload = {
                "configuracao_balcao": json.loads(linha["configuracao_balcao"]),
                "pipeline_secoes": json.loads(linha["pipeline_secoes"]),
            }
        construir_pipeline_desde_json(payload, composicao_calculada)
        composicoes.append(composicao_calculada)
    return composicoes


def _reconstruir_titulos(conn: sqlite3.Connection, pedido_id: int) -> List[str]:
    """Retorna o título de cada opção, na ordem de exibição."""
    return [
        linha["titulo"]
        for linha in repo.listar_layouts(conn, pedido_id)
    ]


def exportar_pdf(conn: sqlite3.Connection, pedido_id: int) -> str:
    """Gera o PDF com uma página por opção salva e devolve o caminho do arquivo."""
    pedido = repo.obter(conn, pedido_id)
    if pedido is None:
        raise ValueError("Pedido não encontrado.")

    composicoes = _reconstruir_composicoes(conn, pedido_id)
    if not composicoes:
        raise ValueError("O pedido não possui opções salvas para exportar.")

    nome_slug = normalizar_slug_cliente(pedido["nome_pedido"])
    caminho_pdf = os.path.join(DIRETORIO_TEMPORARIO, f"layout_{nome_slug}_opcoes.pdf")

    ExportadorPDF.gerar_layouts(
        composicoes,
        _reconstruir_titulos(conn, pedido_id),
        caminho_pdf,
    )
    return caminho_pdf


def exportar_pptx(conn: sqlite3.Connection, pedido_id: int) -> str:
    """Gera o PPTX com um slide por opção salva e devolve o caminho do arquivo."""
    pedido = repo.obter(conn, pedido_id)
    if pedido is None:
        raise ValueError("Pedido não encontrado.")

    composicoes = _reconstruir_composicoes(conn, pedido_id)
    if not composicoes:
        raise ValueError("O pedido não possui opções salvas para exportar.")

    nome_slug = normalizar_slug_cliente(pedido["nome_pedido"])
    caminho_pptx = os.path.join(DIRETORIO_TEMPORARIO, f"layout_{nome_slug}_opcoes.pptx")

    ExportadorPPTX.gerar_layouts(
        composicoes,
        _reconstruir_titulos(conn, pedido_id),
        caminho_pptx,
    )
    return caminho_pptx


def exportar_proposta(conn: sqlite3.Connection, pedido_id: int) -> str:
    """Gera o PDF da Proposta Comercial (página única) e devolve o caminho.

    A Opção 1 (principal) tem o render 3D gerado no servidor (Blender) e
    embutido no PDF; as demais opções aparecem como plantas baixas 2D.
    """
    pedido = repo.obter(conn, pedido_id)
    if pedido is None:
        raise ValueError("Pedido não encontrado.")

    composicoes = _reconstruir_composicoes(conn, pedido_id)
    if not composicoes:
        raise ValueError(
            "O pedido não possui opções salvas para gerar a proposta comercial."
        )

    titulos = _reconstruir_titulos(conn, pedido_id)
    nome_cliente = pedido["nome_cliente"] or pedido["nome_pedido"]
    data = datetime.now().strftime("%d/%m/%Y")

    # Combina as placas (multiplacas) para o render 3D e as medidas do cabeçalho
    itens_combinados, largura_total, profundidade, larguras_placas = (
        combinar_modulos_composicao(composicoes[0])
    )

    # Render 3D da Opção 1 no servidor (falha não derruba o PDF)
    caminho_png: Optional[str] = None
    caminho_jpg: Optional[str] = None
    try:
        itens_render = [
            {
                "nome": item["nome"],
                "formato": item.get("formato", "retangulo"),
                "x": item["x"],
                "y": item["y"],
                "w": item["w"],
                "h": item["h"],
            }
            for item in itens_combinados
        ]
        request = Render3DRequest(
            nome_cliente=nome_cliente,
            largura_balcao_cm=largura_total,
            profundidade_balcao_cm=profundidade,
            itens=itens_render,
            modulos_balcao_cm=larguras_placas if len(larguras_placas) > 1 else None,
        )
        caminho_png, _ = render_service.renderizar_png(request)
        # Embutido em JPEG (qualidade ~85) para reduzir muito o tamanho do PDF
        caminho_jpg = _converter_render_para_jpeg(caminho_png)
    except Exception as e:
        print(f" > [Proposta] Render 3D indisponível ({e}); usando placeholder.")
        caminho_png = None
        caminho_jpg = None

    dados = {
        "nome_cliente": nome_cliente,
        "data": data,
        "largura_cm": largura_total,
        "profundidade_cm": profundidade,
    }
    opcoes = [
        {
            "numero": indice + 1,
            "titulo": titulos[indice] if indice < len(titulos) else "Self-Service Quente",
            "pedido": p,
            "imagem_3d": (caminho_jpg or caminho_png) if indice == 0 else None,
        }
        for indice, p in enumerate(composicoes)
    ]

    nome_slug = normalizar_slug_cliente(pedido["nome_pedido"])
    caminho_pdf = os.path.join(DIRETORIO_TEMPORARIO, f"layout_{nome_slug}_proposta.pdf")

    try:
        ExportadorProposta.gerar(dados, opcoes, caminho_pdf)
    finally:
        for arquivo in (caminho_jpg, caminho_png):
            if arquivo and os.path.exists(arquivo):
                os.unlink(arquivo)
    return caminho_pdf


def _converter_render_para_jpeg(caminho_png: str) -> Optional[str]:
    """Converte o PNG do render 3D para JPEG (menor, para embutir no PDF).

    Retorna o caminho do JPEG, ou `None` se a conversão falhar (o PDF usa o PNG).
    """
    try:
        if not caminho_png or not os.path.exists(caminho_png):
            return None
        caminho_jpg = caminho_png.rsplit(".", 1)[0] + ".jpg"
        with Image.open(caminho_png) as imagem:
            imagem = imagem.convert("RGB")
            if max(imagem.size) > 1100:
                razao = 1100 / max(imagem.size)
                imagem = imagem.resize(
                    (max(1, int(imagem.width * razao)), max(1, int(imagem.height * razao))),
                    Image.LANCZOS,
                )
            imagem.save(caminho_jpg, "JPEG", quality=85, optimize=True)
        return caminho_jpg
    except Exception as e:
        print(f" > [Proposta] Falha ao converter render para JPEG ({e}); usando PNG.")
        return None


def _mapear_layout(linha: Dict[str, Any]) -> LayoutPedidoResposta:
    """Converte uma linha crua do banco em LayoutPedidoResposta."""
    modulos = json.loads(linha["modulos_json"]) if linha.get("modulos_json") else []
    return LayoutPedidoResposta(
        id=str(linha["id"]),
        opcao_numero=int(linha["opcao_numero"]),
        titulo=linha["titulo"],
        configuracao_balcao=json.loads(linha["configuracao_balcao"]),
        pipeline_secoes=json.loads(linha["pipeline_secoes"]),
        modulos=modulos,
    )
