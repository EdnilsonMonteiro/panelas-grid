"""Contratos de dados do módulo de geração de imagens por IA."""

from dataclasses import dataclass
from typing import List


class FalhaGeracaoImagemIAError(RuntimeError):
    """Levantada quando o provedor de imagem falha (rede, autenticação, API)."""


@dataclass(frozen=True)
class SolicitacaoImagemIA:
    """Parâmetros de uma chamada de edição/geração de imagem.

    `imagens` recebe os caminhos das imagens de entrada: a primeira é o
    render 3D (blockout) a ser convertido em foto; as demais são imagens de
    referência (ex.: fotos das panelas vermelhas com interior salpicado).
    """

    prompt: str
    imagens: List[str]
    modelo: str = "gpt-image-2"
    qualidade: str = "medium"
    tamanho: str = "auto"
    quantidade: int = 1
    fundo: str = "auto"
    moderacao: str = "auto"
