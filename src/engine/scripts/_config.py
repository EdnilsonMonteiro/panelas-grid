"""Constantes e caminhos compartilhados do pipeline de render 3D.

Valores extraídos de `blender_render_script.py` (módulo de entrada). Vivem em
um módulo separado para que os demais módulos irmãos (`cenario`, `travessas`,
`comidas`, `iluminacao`, ...) importem sem criar ciclos.
"""

import os

RAIZ_PROJETO = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..")
)

# [Debug] Salva a cena montada em .blend para inspeção manual. Ativo apenas
# com SALVAR_BLEND_DEBUG = true/1/yes (padrão desligado: o save completo da
# cena custa ~1,4 s e não interfere no render final).
SALVAR_BLEND_DEBUG = os.environ.get("SALVAR_BLEND_DEBUG", "").strip().lower() in (
    "true",
    "1",
    "yes",
)
CAMINHO_BLEND_DEBUG = os.path.join(RAIZ_PROJETO, "assets", "debug_ultimo_render.blend")

# Assets de cenário/comida resolvidos a partir dos diretórios do projeto.
GLB_BALCAO = "balcao.glb"
SUBPASTA_COMIDAS = "comidas"
PASTA_TEXTURAS = os.path.join(RAIZ_PROJETO, "assets", "textures")
# HDRI de ambiente: pasta primária conforme a spec (assets/textures/hdri/);
# fallback para assets/hdri/ (layout histórico do repositório).
PASTAS_HDRI = (
    os.path.join(PASTA_TEXTURAS, "hdri"),
    os.path.join(RAIZ_PROJETO, "assets", "hdri"),
)

# Encaixe da comida na boca do recipiente: fração da abertura ocupada (~88%),
# mantendo as bordas do recipiente visíveis ao redor.
FATOR_BOCA_COMIDA = 0.88

# Preenchimento em grade: tamanho alvo de cada célula da grade (garante
# grades >= 2x2 nas cubas de 21 cm), variação de escala por cópia, overlap
# agressivo entre células (1.40: cobre o "vale" do perfil morro dos assets,
# medido em ~10-20% da bbox por borda) e jitter vertical SIMÉTRICO por
# cópia (±2 a 5 mm: quebra o vale coplanar e dá relevo natural sem criar
# superfícies perfeitamente planas). Env vars COMIDA_TRANSBORDO /
# COMIDA_JITTER_Z / COMIDA_SEED permitem experimentos A/B sem editar código.
CELULA_COMIDA_M = 0.10
VARIACAO_ESCALA_COMIDA = 0.02
FATOR_TRANSBORDO_CELULA = float(os.environ.get("COMIDA_TRANSBORDO", "1.40"))
JITTER_Z_MIN_COMIDA_M = 0.002
JITTER_Z_MAX_COMIDA_M = float(os.environ.get("COMIDA_JITTER_Z", "0.005"))
# Anti-folga em recipientes circulares: over-scaling intencional no plano XY
# antes do aparo radial. O alimento ultrapassa a parede interna da panela e o
# corte (bmesh, raio = borda interna) elimina frestas/lacunas nas bordas.
# Calibrado em 1.12 (+12%) por medição de cobertura render top-down: garante
# paridade entre arroz/feijao/macarrao (total escuro 0.9-2.2%); 1.05-1.08
# deixa o arroz com folgas visíveis (~12% do anel). Env COMIDA_EXPANSAO_CIRCULAR
# permite A/B sem editar código.
FATOR_EXPANSAO_CIRCULAR = float(os.environ.get("COMIDA_EXPANSAO_CIRCULAR", "1.12"))

PALETA_PADRAO = [
    (0.62, 0.35, 0.17),  # terracota
    (0.20, 0.45, 0.62),  # azul aço
    (0.35, 0.55, 0.30),  # verde oliva
    (0.65, 0.55, 0.25),  # mostarda
    (0.50, 0.30, 0.45),  # vinho
]

# Fotografia de alimentos: cor quente das luzes principais (~3400 K, tom
# amarelado de restaurante) e intensidade do HDRI de ambiente. Strength 1.0
# calibrado para não estourar os brancos (acima disso o cowboy_town_saloon
# _2k.exr satura a cena). TOM_HDRI multiplica o fundo por um tom levemente
# amarelado para evitar iluminação fria de fundo.
COR_LUZ_QUENTE = (1.0, 0.82, 0.65)
INTENSIDADE_HDRI = 1.0
TOM_HDRI = (1.0, 0.95, 0.88)
SATURACAO_HDRI = 0.85