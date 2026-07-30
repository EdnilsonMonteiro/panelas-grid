"""Repositório de catálogos: acesso direto ao SQLite, sem regras de negócio."""

import sqlite3
from typing import List, Optional


def listar_nomes(conn: sqlite3.Connection) -> List[str]:
    """Retorna os nomes de todos os catálogos, ordenados alfabeticamente."""
    cursor = conn.cursor()
    cursor.execute("SELECT nome_catalogo FROM catalogos ORDER BY nome_catalogo ASC")
    return [linha["nome_catalogo"] for linha in cursor.fetchall()]


def obter_conteudo_json(conn: sqlite3.Connection, nome_catalogo: str) -> Optional[str]:
    """Retorna o JSON bruto do catálogo, ou None se não existir."""
    cursor = conn.cursor()
    cursor.execute(
        "SELECT conteudo_json FROM catalogos WHERE nome_catalogo = ?",
        (nome_catalogo,),
    )
    linha = cursor.fetchone()
    return linha["conteudo_json"] if linha else None


def upsert(conn: sqlite3.Connection, nome_catalogo: str, conteudo_json: str) -> None:
    """Insere ou substitui o conteúdo de um catálogo."""
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT OR REPLACE INTO catalogos (nome_catalogo, conteudo_json)
        VALUES (?, ?)
        """,
        (nome_catalogo.strip(), conteudo_json),
    )


def deletar(conn: sqlite3.Connection, nome_catalogo: str) -> None:
    """Remove um catálogo inteiro do banco."""
    cursor = conn.cursor()
    cursor.execute("DELETE FROM catalogos WHERE nome_catalogo = ?", (nome_catalogo,))
