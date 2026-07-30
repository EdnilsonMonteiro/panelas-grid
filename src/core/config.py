"""Configurações e constantes de diretórios do panelas-grid."""

import os
import tempfile

DIRETORIO_SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAIZ_PROJETO = os.path.abspath(os.path.join(DIRETORIO_SRC, ".."))

DIRETORIO_TEMPORARIO = os.path.join(tempfile.gettempdir(), "layout_engine_outputs")
os.makedirs(DIRETORIO_TEMPORARIO, exist_ok=True)

DIRETORIO_CATALOGOS = os.path.join(RAIZ_PROJETO, "catalogos")
