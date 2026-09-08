"""Provedor OpenAI — API de imagens (`POST /v1/images/edits`).

O import do SDK `openai` é feito sob demanda (dentro do __init__), de modo
que a aplicação continua subindo mesmo sem o pacote instalado — a falha só
acontece quando o recurso de imagem IA é de fato usado.
"""

import base64
import contextlib
import os
import urllib.request

from modules.ia_imagem.ia_imagem_schema import (
    FalhaGeracaoImagemIAError,
    SolicitacaoImagemIA,
)
from modules.ia_imagem.provedores.base import ProvedorImagemIA

TIMEOUT_PADRAO_SEG = 300.0


class ProvedorOpenAI(ProvedorImagemIA):
    """Implementa o contrato via SDK oficial `openai` (modelos gpt-image-*)."""

    nome = "openai"

    def __init__(self, api_key: str = "", timeout_seg: float = 0.0):
        try:
            from openai import OpenAI
        except ImportError as e:
            raise FalhaGeracaoImagemIAError(
                "Pacote 'openai' não instalado (pip install -U openai)."
            ) from e

        chave = (api_key or os.environ.get("OPENAI_API_KEY", "")).strip()
        if not chave:
            raise FalhaGeracaoImagemIAError(
                "OPENAI_API_KEY não definida no ambiente (ou no .env)."
            )
        self._client = OpenAI(api_key=chave, timeout=self._timeout_seg(timeout_seg))

    @staticmethod
    def _timeout_seg(timeout_seg: float) -> float:
        if timeout_seg > 0:
            return timeout_seg
        bruto = os.environ.get("IMAGE_AI_TIMEOUT", "").strip()
        try:
            return float(bruto) if bruto else TIMEOUT_PADRAO_SEG
        except ValueError:
            return TIMEOUT_PADRAO_SEG

    def gerar_imagem_editada(self, solicitacao: SolicitacaoImagemIA) -> bytes:
        if not solicitacao.imagens:
            raise FalhaGeracaoImagemIAError(
                "Nenhuma imagem de entrada informada para a edição."
            )
        for caminho in solicitacao.imagens:
            if not os.path.exists(caminho):
                raise FalhaGeracaoImagemIAError(
                    f"Imagem de entrada não encontrada: {caminho}"
                )

        try:
            with contextlib.ExitStack() as pilha:
                arquivos = [
                    pilha.enter_context(open(caminho, "rb"))
                    for caminho in solicitacao.imagens
                ]
                # Método do SDK é `edit` (singular); o endpoint REST é
                # /v1/images/edits. `moderation` só existe em images.generate.
                resposta = self._client.images.edit(
                    image=arquivos,
                    prompt=solicitacao.prompt,
                    model=solicitacao.modelo,
                    n=solicitacao.quantidade,
                    size=solicitacao.tamanho,
                    quality=solicitacao.qualidade,
                    background=solicitacao.fundo,
                )
        except FalhaGeracaoImagemIAError:
            raise
        except Exception as e:
            raise FalhaGeracaoImagemIAError(f"Erro na API OpenAI: {e}") from e

        dados = resposta.data[0]
        if getattr(dados, "b64_json", None):
            return base64.b64decode(dados.b64_json)
        url = getattr(dados, "url", None)
        if url:
            try:
                with urllib.request.urlopen(url, timeout=60) as resposta_url:
                    return resposta_url.read()
            except Exception as e:
                raise FalhaGeracaoImagemIAError(
                    f"Falha ao baixar a imagem gerada: {e}"
                ) from e
        raise FalhaGeracaoImagemIAError("A API não devolveu b64_json nem url.")
