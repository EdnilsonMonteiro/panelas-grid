"""Repositório de pedidos do cliente e layouts: acesso direto ao SQLite."""

import sqlite3
from typing import Any, Dict, List, Optional


def listar_pedidos(
    conn: sqlite3.Connection,
    limite: Optional[int] = None,
    busca: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Retorna os pedidos (mais recentes primeiro), com quantidade de layouts.

    `limite` restringe o nº de resultados (pedidos recentes) e `busca` filtra
    por nome do pedido ou nome do cliente (LIKE).
    """
    query = """
        SELECT p.id, p.nome_pedido, p.nome_cliente,
               (SELECT COUNT(*) FROM layouts_pedido l WHERE l.pedido_id = p.id) AS qtd_layouts
        FROM pedidos_cliente p
    """
    parametros: List[Any] = []
    if busca:
        query += " WHERE p.nome_pedido LIKE ? OR p.nome_cliente LIKE ?"
        termo = f"%{busca}%"
        parametros.extend([termo, termo])
    query += " ORDER BY p.criado_em DESC, p.id DESC"
    if limite:
        query += " LIMIT ?"
        parametros.append(limite)

    cursor = conn.cursor()
    cursor.execute(query, parametros)
    return [dict(linha) for linha in cursor.fetchall()]


def criar(conn: sqlite3.Connection, nome_pedido: str, nome_cliente: str) -> int:
    """Cria um pedido e devolve o id gerado."""
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO pedidos_cliente (nome_pedido, nome_cliente) VALUES (?, ?)",
        (nome_pedido, nome_cliente),
    )
    return int(cursor.lastrowid)


def deletar_pedido(conn: sqlite3.Connection, pedido_id: int) -> None:
    """Remove um pedido (layouts associados são removidos via CASCADE)."""
    cursor = conn.cursor()
    cursor.execute("DELETE FROM pedidos_cliente WHERE id = ?", (pedido_id,))


def obter(conn: sqlite3.Connection, pedido_id: int) -> Optional[Dict[str, Any]]:
    """Retorna um pedido pelo id, ou None se não existir."""
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, nome_pedido, nome_cliente FROM pedidos_cliente WHERE id = ?",
        (pedido_id,),
    )
    linha = cursor.fetchone()
    return dict(linha) if linha else None


def atualizar_nome_cliente(
    conn: sqlite3.Connection, pedido_id: int, nome_cliente: str
) -> None:
    """Atualiza o nome do cliente do pedido (usado no cabeçalho do export)."""
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE pedidos_cliente SET nome_cliente = ? WHERE id = ?",
        (nome_cliente, pedido_id),
    )


def atualizar_nome_pedido(
    conn: sqlite3.Connection, pedido_id: int, nome_pedido: str
) -> None:
    """Atualiza o nome de exibição do pedido."""
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE pedidos_cliente SET nome_pedido = ? WHERE id = ?",
        (nome_pedido, pedido_id),
    )


def listar_layouts(conn: sqlite3.Connection, pedido_id: int) -> List[Dict[str, Any]]:
    """Retorna os layouts do pedido ordenados pelo número da opção."""
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT id, opcao_numero, titulo, categoria, configuracao_balcao,
               pipeline_secoes, modulos_json
        FROM layouts_pedido
        WHERE pedido_id = ?
        ORDER BY opcao_numero ASC, id ASC
        """,
        (pedido_id,),
    )
    return [dict(linha) for linha in cursor.fetchall()]


def listar_categorias(conn: sqlite3.Connection, pedido_id: int) -> List[str]:
    """Retorna as categorias (grupos de exportação) já usadas no pedido."""
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT DISTINCT categoria FROM layouts_pedido
        WHERE pedido_id = ? AND categoria != ''
        ORDER BY categoria ASC
        """,
        (pedido_id,),
    )
    return [linha["categoria"] for linha in cursor.fetchall()]


def proximo_numero_opcao(conn: sqlite3.Connection, pedido_id: int) -> int:
    """Calcula o próximo número de opção disponível para o pedido."""
    cursor = conn.cursor()
    cursor.execute(
        "SELECT COALESCE(MAX(opcao_numero), 0) + 1 FROM layouts_pedido WHERE pedido_id = ?",
        (pedido_id,),
    )
    return int(cursor.fetchone()[0])


def inserir_layout(
    conn: sqlite3.Connection,
    pedido_id: int,
    opcao_numero: int,
    titulo: str,
    configuracao_balcao_json: str,
    pipeline_secoes_json: str,
    modulos_json: Optional[str] = None,
    categoria: str = "",
) -> int:
    """Insere um novo layout no pedido e devolve o id gerado."""
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO layouts_pedido
            (pedido_id, opcao_numero, titulo, configuracao_balcao,
             pipeline_secoes, modulos_json, categoria)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            pedido_id,
            opcao_numero,
            titulo,
            configuracao_balcao_json,
            pipeline_secoes_json,
            modulos_json,
            categoria,
        ),
    )
    return int(cursor.lastrowid)


def obter_layout(conn: sqlite3.Connection, layout_id: int) -> Optional[Dict[str, Any]]:
    """Retorna um layout pelo id, ou None se não existir."""
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT id, pedido_id, opcao_numero, titulo, categoria, configuracao_balcao,
               pipeline_secoes, modulos_json
        FROM layouts_pedido WHERE id = ?
        """,
        (layout_id,),
    )
    linha = cursor.fetchone()
    return dict(linha) if linha else None


def atualizar_categoria(conn: sqlite3.Connection, layout_id: int, categoria: str) -> None:
    """Atualiza a categoria (grupo de exportação) de uma opção.

    A categoria é a fonte lógica do nome: quando não vazia, o `titulo`
    (texto exibido no PDF/PPTX) é espelhado para o mesmo valor.
    """
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE layouts_pedido
        SET categoria = ?,
            titulo = CASE WHEN ? != '' THEN ? ELSE titulo END
        WHERE id = ?
        """,
        (categoria, categoria, categoria, layout_id),
    )


def atualizar_layout(
    conn: sqlite3.Connection,
    layout_id: int,
    titulo: str,
    configuracao_balcao_json: str,
    pipeline_secoes_json: str,
    modulos_json: Optional[str] = None,
    categoria: Optional[str] = None,
) -> None:
    """Atualiza o conteúdo de um layout (opção) existente.

    `categoria` é opcional: quando None, mantém a categoria atual.
    """
    cursor = conn.cursor()
    if categoria is None:
        cursor.execute(
            """
            UPDATE layouts_pedido
            SET titulo = ?, configuracao_balcao = ?, pipeline_secoes = ?, modulos_json = ?
            WHERE id = ?
            """,
            (titulo, configuracao_balcao_json, pipeline_secoes_json, modulos_json, layout_id),
        )
    else:
        cursor.execute(
            """
            UPDATE layouts_pedido
            SET titulo = ?, configuracao_balcao = ?, pipeline_secoes = ?, modulos_json = ?,
                categoria = ?
            WHERE id = ?
            """,
            (
                titulo,
                configuracao_balcao_json,
                pipeline_secoes_json,
                modulos_json,
                categoria,
                layout_id,
            ),
        )


def deletar_layout(conn: sqlite3.Connection, layout_id: int) -> None:
    """Remove um layout pelo id."""
    cursor = conn.cursor()
    cursor.execute("DELETE FROM layouts_pedido WHERE id = ?", (layout_id,))


def renumerar(conn: sqlite3.Connection, pedido_id: int) -> None:
    """Renumera sequencialmente (1..N) as opções de um pedido."""
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT id FROM layouts_pedido
        WHERE pedido_id = ?
        ORDER BY opcao_numero ASC, id ASC
        """,
        (pedido_id,),
    )
    for novo_numero, linha in enumerate(cursor.fetchall(), start=1):
        cursor.execute(
            "UPDATE layouts_pedido SET opcao_numero = ? WHERE id = ?",
            (novo_numero, linha["id"]),
        )


def reordenar(conn: sqlite3.Connection, ordered_layout_ids: List[int]) -> None:
    """Reatribui os números de opção na ordem final desejada."""
    cursor = conn.cursor()
    for novo_numero, layout_id in enumerate(ordered_layout_ids, start=1):
        cursor.execute(
            "UPDATE layouts_pedido SET opcao_numero = ? WHERE id = ?",
            (novo_numero, layout_id),
        )
