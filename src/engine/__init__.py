"""Pacote `engine` do panelas-grid.

Mantém a compatibilidade retroativa com o antigo módulo `engine.py`:
`from engine import LayoutEngine` continua funcionando normalmente.
"""

from engine.layout import LayoutEngine

__all__ = ["LayoutEngine"]
