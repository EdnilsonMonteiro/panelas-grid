"""Configurações e constantes de diretórios do panelas-grid."""

import os
import tempfile

DIRETORIO_SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAIZ_PROJETO = os.path.abspath(os.path.join(DIRETORIO_SRC, ".."))

DIRETORIO_TEMPORARIO = os.path.join(tempfile.gettempdir(), "layout_engine_outputs")
os.makedirs(DIRETORIO_TEMPORARIO, exist_ok=True)

DIRETORIO_CATALOGOS = os.path.join(RAIZ_PROJETO, "catalogos")

DIRETORIO_REPORTS = os.path.join(RAIZ_PROJETO, "assets", "reports")

_VALORES_ENV_VERDADEIROS = {"true", "1", "yes"}


def env_habilitada(nome: str, padrao: bool = False) -> bool:
    """Interpreta uma variável de ambiente booleana.

    Valores aceitos (case-insensitive): 'true', '1', 'yes'.
    Ausência ou qualquer outro valor equivale a `padrao`.
    """
    valor = os.environ.get(nome)
    if valor is None:
        return padrao
    return valor.strip().lower() in _VALORES_ENV_VERDADEIROS
