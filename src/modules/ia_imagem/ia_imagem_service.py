"""Serviço de geração de imagens realistas via APIs de IA (provider-agnostic).

O render 3D do Blender (blockout) é enviado como imagem base para a API,
junto com fotos de referência das panelas; a resposta é uma foto
fotorrealista do mesmo arranjo, preservando posição e quantidade das
travessas. A foto substitui o render 3D no PDF da Proposta Comercial.

Configuração por variáveis de ambiente (carregadas do .env em app.py):
    ENABLE_IMAGE_AI              -> liga/desliga o recurso (padrão: true)
    IMAGE_AI_PROVIDER            -> provedor registrado em _PROVEDORES (openai)
    IMAGE_AI_MODEL               -> modelo do provedor (gpt-image-2)
    IMAGE_AI_QUALITY             -> qualidade (low | medium | high | auto)
    IMAGE_AI_SIZE                -> tamanho da saída (padrão: auto)
    IMAGE_AI_TIMEOUT             -> timeout da chamada em segundos (300)
    IMAGE_AI_IMAGENS_REFERENCIA  -> caminhos de referência extras (';' ou ',')
    OPENAI_API_KEY               -> credencial do provedor OpenAI
"""

import os
import uuid
from typing import Dict, List, Optional, Type

from core.config import DIRETORIO_TEMPORARIO, RAIZ_PROJETO, env_habilitada
from modules.ia_imagem.ia_imagem_prompts import PROMPT_FOTO_REALISTA_BUFFET
from modules.ia_imagem.ia_imagem_schema import (
    FalhaGeracaoImagemIAError,
    SolicitacaoImagemIA,
)
from modules.ia_imagem.provedores.base import ProvedorImagemIA
from modules.ia_imagem.provedores.openai_provedor import ProvedorOpenAI

# Registro dos provedores disponíveis (chave = IMAGE_AI_PROVIDER).
# Novos fornecedores: criar a subclasse e adicioná-la aqui.
_PROVEDORES: Dict[str, Type[ProvedorImagemIA]] = {
    "openai": ProvedorOpenAI,
}

# Fotos de referência das panelas (exterior vermelho brilhante, interior
# preto fosco salpicado de branco) citadas no prompt como image_0/image_1.
_REFERENCIAS_PADRAO = (
    os.path.join(RAIZ_PROJETO, "assets", "panela_redonda.png"),
    os.path.join(RAIZ_PROJETO, "assets", "panela_retangular.png"),
)


def imagem_ia_habilitada() -> bool:
    """Chave geral do recurso (desliga sem remover credenciais do .env)."""
    return env_habilitada("ENABLE_IMAGE_AI", padrao=True)


def _obter_provedor() -> ProvedorImagemIA:
    """Instancia o provedor configurado em IMAGE_AI_PROVIDER."""
    nome = (os.environ.get("IMAGE_AI_PROVIDER", "openai") or "openai").strip().lower()
    classe = _PROVEDORES.get(nome)
    if classe is None:
        raise FalhaGeracaoImagemIAError(
            f"Provedor de imagem '{nome}' desconhecido. "
            f"Disponíveis: {', '.join(sorted(_PROVEDORES))}."
        )
    return classe()


def _imagens_referencia() -> List[str]:
    """Imagens de referência das panelas (o render 3D é anexado à parte).

    Sobrescrevível via IMAGE_AI_IMAGENS_REFERENCIA (caminhos separados por
    ';' ou ','); inexistentes são descartados silenciosamente.
    """
    brutas = os.environ.get("IMAGE_AI_IMAGENS_REFERENCIA", "").strip()
    if brutas:
        return [
            parte.strip()
            for parte in brutas.replace(";", ",").split(",")
            if parte.strip() and os.path.exists(parte.strip())
        ]
    return [caminho for caminho in _REFERENCIAS_PADRAO if os.path.exists(caminho)]


def gerar_foto_realista_buffet(
    caminho_render_3d: str, caminho_saida: Optional[str] = None
) -> str:
    """Converte o render 3D (blockout) em foto realista via API de imagem.

    O render preserva a disposição exata das travessas; a API adiciona o
    realismo (comidas, iluminação, revestimento das panelas). Retorna o
    caminho do arquivo gerado (PNG). Levanta `FalhaGeracaoImagemIAError` em
    qualquer falha — o chamador decide o fallback (ex.: usar o próprio render).
    """
    if not caminho_render_3d or not os.path.exists(caminho_render_3d):
        raise FalhaGeracaoImagemIAError(
            f"Render 3D de referência não encontrado: {caminho_render_3d}"
        )

    provedor = _obter_provedor()
    destino = caminho_saida or os.path.join(
        DIRETORIO_TEMPORARIO, f"ia_foto_buffet_{uuid.uuid4().hex[:8]}.png"
    )

    solicitacao = SolicitacaoImagemIA(
        prompt=PROMPT_FOTO_REALISTA_BUFFET,
        imagens=[caminho_render_3d, *_imagens_referencia()],
        modelo=(os.environ.get("IMAGE_AI_MODEL", "gpt-image-2") or "gpt-image-2").strip(),
        qualidade=(os.environ.get("IMAGE_AI_QUALITY", "medium") or "medium").strip(),
        tamanho=(os.environ.get("IMAGE_AI_SIZE", "auto") or "auto").strip(),
    )

    conteudo = provedor.gerar_imagem_editada(solicitacao)
    with open(destino, "wb") as arquivo:
        arquivo.write(conteudo)
    return destino
