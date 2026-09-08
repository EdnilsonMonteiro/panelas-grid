"""Contrato abstrato de um provedor de geração de imagens por IA.

Para suportar um novo fornecedor (Google, Stability, Replicate...), crie uma
subclasse de `ProvedorImagemIA` e registre-a no dicionário `_PROVEDORES` de
`ia_imagem_service`. Nenhum outro ponto do sistema conhece a API concreta.
"""

from abc import ABC, abstractmethod

from modules.ia_imagem.ia_imagem_schema import SolicitacaoImagemIA


class ProvedorImagemIA(ABC):
    """Interface única consumida pelo serviço; isola o fornecedor concreto."""

    nome: str = "base"

    @abstractmethod
    def gerar_imagem_editada(self, solicitacao: SolicitacaoImagemIA) -> bytes:
        """Executa a edição/geração e devolve os bytes da imagem resultante.

        Deve levantar `FalhaGeracaoImagemIAError` em qualquer falha
        (autenticação, rede, parâmetros, resposta inválida).
        """
