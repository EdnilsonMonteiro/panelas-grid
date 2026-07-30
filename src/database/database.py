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

    conn.commit()
    conn.close()
    print(" > Banco de dados SQLite inicializado e verificado com sucesso.")
