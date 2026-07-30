"""Regras de negócio de templates de pipeline."""

import json
import sqlite3
from typing import List

from . import template_repository as repo_templates
from .template_schema import TemplatePipelineEntrada, TemplatePipelineResposta


def listar_templates(conn: sqlite3.Connection) -> List[TemplatePipelineResposta]:
    """Retorna todos os templates salvos, com as seções já desserializadas."""
    return [
        TemplatePipelineResposta(
            id=str(linha["id"]),
            nome_template=linha["nome_template"],
            pipeline_secoes=json.loads(linha["pipeline_secoes"]),
        )
        for linha in repo_templates.listar(conn)
    ]


def salvar_template(conn: sqlite3.Connection, dados: TemplatePipelineEntrada) -> None:
    """Grava (upsert) um template de pipeline configurado pela UI."""
    pipeline_json = json.dumps(
        [secao.model_dump(mode="json") for secao in dados.pipeline_secoes],
        ensure_ascii=False,
    )
    repo_templates.upsert(conn, dados.nome_template, pipeline_json)


def deletar_template(conn: sqlite3.Connection, id_template: int) -> None:
    """Remove um template de pipeline pelo id."""
    repo_templates.deletar(conn, id_template)
