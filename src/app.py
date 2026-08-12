"""API do panelas-grid — aplicação FastAPI unificada.

Entrypoint do servidor (porta 8000). Registra os routers modulares:
    - routers.catalogos   -> /api/catalogos
    - routers.templates   -> /api/templates
    - routers.pipeline    -> /api/schemas, /api/processar
    - routers.exportacao  -> /api/download-pptx/{nome_slug}
    - routers.render      -> /api/v1/buffet/render-3d (Blender Eevee headless)

Execução:
    cd panelas-grid/src
    python app.py            # ou: uvicorn app:app --port 8000
"""

import os
import sys

import uvicorn
from database.database import inicializar_banco
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from modules.catalogos import catalogo_router as catalogos
from modules.exportacao import exportacao_router as exportacao
from modules.pedidos import pedido_router as pedidos
from modules.pipeline import pipeline_router as pipeline
from modules.render import render_router as render
from modules.templates import template_router as templates

# Garante que o diretório deste arquivo (src/) esteja no sys.path mesmo quando
# o módulo for carregado como `src.app` a partir da raiz do projeto.
DIRETORIO_SRC = os.path.dirname(os.path.abspath(__file__))
if DIRETORIO_SRC not in sys.path:
    sys.path.insert(0, DIRETORIO_SRC)

# Carrega variáveis de ambiente do arquivo .env (raiz do projeto e/ou src/).
# Variáveis já definidas no ambiente do sistema têm precedência sobre o .env.
load_dotenv(os.path.join(os.path.dirname(DIRETORIO_SRC), ".env"))
load_dotenv(os.path.join(DIRETORIO_SRC, ".env"))


inicializar_banco()

app = FastAPI(title="panelas-grid — Motor de Layout e Renderização 3D", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(catalogos.router)
app.include_router(templates.router)
app.include_router(pipeline.router)
app.include_router(pipeline.router_v1)
app.include_router(exportacao.router)
app.include_router(pedidos.router)
app.include_router(render.router)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
