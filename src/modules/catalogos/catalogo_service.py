"""Regras de negócio de catálogos de travessas/cubas."""

import json
import os
import sqlite3
from typing import Any, Dict, List

from core.config import DIRETORIO_CATALOGOS
from core.dependencies import conexao_db

from . import template_repository as repo_catalogos
from .catalogo_schema import ItemCatalogo

CATALOGOS_PADRAO = ["catalogo_mestre", "catalogo_gaps", "catalogo_saladas"]


def listar_nomes_catalogos(conn: sqlite3.Connection) -> List[str]:
    """Lista os catálogos gravados; devolve os nomes padrão se o banco estiver vazio."""
    nomes = repo_catalogos.listar_nomes(conn)
    return nomes if nomes else list(CATALOGOS_PADRAO)


def obter_itens_catalogo(
    conn: sqlite3.Connection, nome_catalogo: str
) -> List[Dict[str, Any]]:
    """Retorna os itens de um catálogo (lista vazia se inexistente)."""
    conteudo = repo_catalogos.obter_conteudo_json(conn, nome_catalogo)
    return json.loads(conteudo) if conteudo else []


def salvar_itens_catalogo(
    conn: sqlite3.Connection, nome_catalogo: str, itens: List[ItemCatalogo]
) -> None:
    """Persiste (upsert) a lista de itens de um catálogo."""
    conteudo_json = json.dumps(
        [item.model_dump() for item in itens], ensure_ascii=False
    )
    repo_catalogos.upsert(conn, nome_catalogo, conteudo_json)


def deletar_catalogo(conn: sqlite3.Connection, nome_catalogo: str) -> None:
    """Remove um catálogo inteiro."""
    repo_catalogos.deletar(conn, nome_catalogo)


def carregar_catalogo_por_nome(nome_catalogo: str) -> List[Dict[str, Any]]:
    """Carrega um catálogo pelo nome: SQLite primeiro, arquivo físico como fallback.

    Abre conexão própria de curta duração (uso interno do motor geométrico,
    fora do ciclo de requisição dos routers).
    """
    try:
        with conexao_db() as conn:
            conteudo = repo_catalogos.obter_conteudo_json(conn, nome_catalogo)
        if conteudo:
            return json.loads(conteudo)
    except Exception as e:
        print(f"Erro ao acessar SQLite para catálogo: {e}")

    caminho_arquivo = os.path.join(DIRETORIO_CATALOGOS, f"{nome_catalogo}.json")
    if os.path.exists(caminho_arquivo):
        with open(caminho_arquivo, "r", encoding="utf-8") as f:
            print(
                f" > [Aviso] Catálogo '{nome_catalogo}' carregado via arquivo físico (Fallback)."
            )
            return json.load(f)

    return []
