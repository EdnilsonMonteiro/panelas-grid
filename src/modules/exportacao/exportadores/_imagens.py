"""Otimização de imagens usadas nos exportadores (PDF/PPTX/Proposta).

As panelas (`panela_redonda.png` / `panela_retangular.png`) são PNGs de alta
resolução (~1,1 MB) que, embutidos na resolução cheia, inflam o PDF/PPTX e
tornam a geração mais lenta. Este módulo gera (e guarda em cache) versões
reduzidas adequadas ao tamanho em que são desenhadas na página, sem perda
visual perceptível.
"""

import os
from functools import lru_cache
from pathlib import Path
from typing import Optional

from PIL import Image

from core.config import DIRETORIO_TEMPORARIO

ARQUIVO_ATUAL = Path(__file__).resolve()
PASTA_RAIZ_PROJETO = next(
    p for p in ARQUIVO_ATUAL.parents if (p / "assets").exists() or (p / "src").exists()
)
PASTA_ASSETS = PASTA_RAIZ_PROJETO / "assets"

MAX_PX_PADRAO = 300


@lru_cache(maxsize=None)
def caminho_panela_otimizado(nome_arquivo: str, max_px: int = MAX_PX_PADRAO) -> Optional[str]:
    """Gera (uma única vez) a versão reduzida de uma panela e devolve o caminho.

    Retorna `None` se o arquivo original não existir — o chamador deve usar o
    fallback de formas geométricas.
    """
    origem = PASTA_ASSETS / nome_arquivo
    if not origem.exists():
        return None

    destino = os.path.join(DIRETORIO_TEMPORARIO, f"_otimizada_{max_px}_{nome_arquivo}")
    if os.path.exists(destino):
        return destino

    with Image.open(origem) as imagem:
        imagem = imagem.convert("RGBA")
        if max(imagem.size) > max_px:
            razao = max_px / max(imagem.size)
            novo_tamanho = (
                max(1, int(imagem.width * razao)),
                max(1, int(imagem.height * razao)),
            )
            imagem = imagem.resize(novo_tamanho, Image.LANCZOS)
        imagem.save(destino, "PNG", optimize=True)

    return destino
