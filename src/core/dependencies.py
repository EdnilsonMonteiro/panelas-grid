"""Injeção de dependência de banco de dados para os routers FastAPI."""

import sqlite3
from contextlib import contextmanager
from typing import Generator

from database.database import obter_conexao


@contextmanager
def conexao_db() -> Generator[sqlite3.Connection, None, None]:
    """Context manager: abre conexão, faz commit em caso de sucesso e sempre fecha."""
    conn = obter_conexao()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_db() -> Generator[sqlite3.Connection, None, None]:
    """Dependência FastAPI (Depends) que injeta uma conexão SQLite por requisição."""
    with conexao_db() as conn:
        yield conn
