import os
import sqlite3

DIRETORIO_ATUAL = os.path.dirname(os.path.abspath(__file__))
CAMINHO_BANCO = os.path.join(DIRETORIO_ATUAL, "dados.db")


def obter_conexao():
    """Retorna uma conexão com o banco de dados que mapeia linhas como dicionários.

    `check_same_thread=False` é necessário porque o FastAPI executa endpoints
    síncronos (def) e dependências (Depends) em um pool de threads: a conexão
    pode ser aberta em um thread e usada/fechada em outro. É seguro porque cada
    requisição possui sua própria conexão — o uso entre threads é sequencial,
    nunca concorrente sobre o mesmo objeto de conexão.
    """
    conn = sqlite3.connect(CAMINHO_BANCO, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def inicializar_banco():
    """Cria as tabelas necessárias se elas não existirem."""
    conn = obter_conexao()
    cursor = conn.cursor()

    # 1. Tabela de Modelos/Templates de Ordem de Execução
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS templates_pipeline (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome_template TEXT NOT NULL UNIQUE,
            pipeline_secoes TEXT NOT NULL -- Armazenará o JSON como string
        )
    """)

    # 2. Tabela de Catálogos
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS catalogos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome_catalogo TEXT NOT NULL UNIQUE,
            conteudo_json TEXT NOT NULL -- Lista de cubas/panelas salvas em formato JSON
        )
    """)

    # 3. Tabela de Pedidos do Cliente
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pedidos_cliente (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome_pedido TEXT NOT NULL,
            nome_cliente TEXT NOT NULL DEFAULT '',
            criado_em TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)

    # 4. Tabela de Layouts (Opções) de cada Pedido
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS layouts_pedido (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pedido_id INTEGER NOT NULL REFERENCES pedidos_cliente(id) ON DELETE CASCADE,
            opcao_numero INTEGER NOT NULL,
            titulo TEXT NOT NULL DEFAULT 'Self-Service Quente',
            configuracao_balcao TEXT NOT NULL, -- Configuração do balcão em formato JSON
            pipeline_secoes TEXT NOT NULL, -- Seções do pipeline em formato JSON
            criado_em TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)

    # Migração: coluna de multiplacas (opções com várias placas)
    colunas = [linha[1] for linha in cursor.execute("PRAGMA table_info(layouts_pedido)").fetchall()]
    if "modulos_json" not in colunas:
        cursor.execute(
            "ALTER TABLE layouts_pedido ADD COLUMN modulos_json TEXT"
        )

    # Migração: categoria (grupo de exportação) de cada opção — permite
    # exportar PDF/PPTX/Proposta isolados (ex.: "Balcão Quente" / "Balcão Frio")
    if "categoria" not in colunas:
        cursor.execute(
            "ALTER TABLE layouts_pedido ADD COLUMN categoria TEXT NOT NULL DEFAULT ''"
        )

    conn.commit()
    conn.close()
    print(" > Banco de dados SQLite inicializado e verificado com sucesso.")
