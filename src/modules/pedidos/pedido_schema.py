"""Contratos de pedidos do cliente e seus layouts (opções)."""

from typing import Any, Dict, List

from modules.pipeline.pipeline_schema import (
    ConfiguracaoBalcao,
    ModuloConfig,
    SecaoPipeline,
)
from pydantic import BaseModel, Field, field_validator


class PedidoEntrada(BaseModel):
    """Payload de criação de um novo pedido do cliente.

    `nome_pedido` é opcional: quando ausente/vazio o serviço gera um
    timestamp legível (ex.: "12/08/2026 14:35:22") como identificador.
    """

    nome_pedido: str | None = Field(
        default=None, description="Nome do pedido (opcional; vira timestamp se vazio)"
    )
    nome_cliente: str = Field(default="", description="Nome do cliente exibido no export")

    @field_validator("nome_pedido")
    @classmethod
    def nome_nao_vazio(cls, valor: str | None) -> str | None:
        if valor is None:
            return None
        valor = valor.strip()
        return valor or None


class LayoutPedidoEntrada(BaseModel):
    """Payload de gravação de uma nova opção (layout) no pedido."""

    titulo: str = Field(default="Self-Service Quente")
    categoria: str = Field(
        default="",
        description="Grupo de exportação da opção (ex.: Balcão Quente / Balcão Frio)",
    )
    configuracao_balcao: ConfiguracaoBalcao
    pipeline_secoes: List[SecaoPipeline] = Field(min_length=1)
    modulos: List[ModuloConfig] = Field(
        default_factory=list, description="Multiplacas da opção (opcional)"
    )


class LayoutPedidoResposta(BaseModel):
    """Opção persistida, devolvida na listagem para a UI."""

    id: str
    opcao_numero: int
    titulo: str
    categoria: str = ""
    configuracao_balcao: Dict[str, Any]
    pipeline_secoes: List[Dict[str, Any]]
    modulos: List[Dict[str, Any]] = Field(default_factory=list)


class PedidoListaResposta(BaseModel):
    """Item da lista de pedidos (para o seletor da UI)."""

    id: str
    nome_pedido: str
    nome_cliente: str
    qtd_layouts: int


class PedidoResposta(BaseModel):
    """Pedido completo com seus layouts, devolvido para a UI."""

    id: str
    nome_pedido: str
    nome_cliente: str
    layouts: List[LayoutPedidoResposta]


class ReordenarLayoutsEntrada(BaseModel):
    """Payload de reordenação das opções (ordem final desejada)."""

    ordered_layout_ids: List[int] = Field(min_length=1)


class CategoriaLayoutEntrada(BaseModel):
    """Payload de atualização da categoria (grupo de exportação) de uma opção."""

    categoria: str = Field(default="", description="Nome do grupo (vazio = sem grupo)")


class PedidoAtualizarEntrada(BaseModel):
    """Payload de atualização parcial de um pedido."""

    nome_pedido: str | None = Field(default=None, min_length=1)
    nome_cliente: str | None = None
