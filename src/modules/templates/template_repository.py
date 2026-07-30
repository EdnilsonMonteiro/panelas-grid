"""Repositório de templates de pipeline: acesso direto ao SQLite."""

import sqlite3
from typing import Any, Dict, List


def listar(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    """Retorna todos os templates (id, nome e JSON das seções) crus do banco."""
    cursor = conn.cursor()
    cursor.execute("SELECT id, nome_template, pipeline_secoes FROM templates_pipeline")
    return [dict(linha) for linha in cursor.fetchall()]


def upsert(conn: sqlite3.Connection, nome_template: str, pipeline_json: str) -> None:
    """Insere ou substitui um template de pipeline."""
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR REPLACE INTO templates_pipeline (nome_template, pipeline_secoes) VALUES (?, ?)",
        (nome_template, pipeline_json),
    )


def deletar(conn: sqlite3.Connection, id_template: int) -> None:
    """Remove um template pelo id."""
    cursor = conn.cursor()
    cursor.execute("DELETE FROM templates_pipeline WHERE id = ?", (id_template,))
