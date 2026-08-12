"""Script executado INTERNAMENTE pelo Blender (modo headless).

Uso:
    blender -b -P blender_render_script.py -- <json_inline_ou_caminho_json>

Responsabilidades (conforme SPEC_3D_RENDER.md):
    1. Carregar `templates/cenario_template.blend` (se existir; caso contrário
       monta um cenário procedural equivalente).
    2. Ler os argumentos JSON enviados pela linha de comando.
    3. Importar o `balcao.glb` e escalá-lo parametricamente em X (largura) e
       Y (profundidade) para casar com as dimensões do payload; as travessas
       são posicionadas em Z no topo do tampo da mesa escalada. Fallback:
       balcão procedural (corpo + tampo).
    4. Importar os arquivos `.glb` das travessas e aplicar as transformações
       de posição (x, y, z). Travessas sem `.glb` recebem uma malha procedural
       (cilindro para formato "circulo", caixa para "retangulo").
    5. Sortear comidas de `assets/glb/comidas/` via deck sem repetição
       (FoodDeckManager) e preenchê-las em grade N x M dentro das cubas
       retangulares com anti-tiling (rotação Z aleatória em 0/90/180/270°,
       espelhamento aleatório em X/Y em 50% das células, jitter de altura Z
       ±2-5 mm e variação de escala por cópia), preservando as bordas
       visíveis. Formato "circulo" sorteia apenas entre arroz/feijao/
       macarrao (peça única).
    6. Erguer piso e parede como planos procedurais com materiais PBR
       construídos a partir de `assets/textures/piso/` (tiling via nó
       Mapping) e `assets/textures/parede/` (detecta dinamicamente mapa
       Specular vs Roughness).
    7. Iluminar a cena como estúdio de fotografia de alimentos: World HDRI
       dinâmico de `assets/textures/hdri/` (`.hdr`/`.exr`, Strength 0.8) +
       2 area lights quentes (~3800 K, 30-80 W) acima e inclinadas sobre o
       balcão, calibradas para não estourar os brancos.
    8. Desenhar cotas dimensionais (linhas CURVE brancas emissivas + textos
       FONT com constraint de rotação para a câmera) em metros.
    9. Configurar o renderizador `BLENDER_EEVEE_NEXT`, o color management
       (`AgX` com fallback `Filmic`, look Medium High Contrast/None, exposure
       -0.85 e Curve Mapping com canal R aquecido ~3400 K), o bloom suave
       (threshold 3.5) e gerar a imagem `.png`.

Contrato do JSON de entrada (todas as medidas em METROS, coordenadas no
CENTRO da peça, eixo Z apontando para cima):
    {
        "template_path": "caminho/para/cenario_template.blend",
        "output_path":   "caminho/para/render.png",
        "glb_dir":       "caminho/para/assets/glb",
        "balcao": {"largura_m": 1.90, "profundidade_m": 0.95,
                   "altura_m": 0.90, "espessura_tampo_m": 0.05},
        "camera": {"angulo_elevacao_graus": 75.0, "fator_margem": 1.30},
        "cotas":  {"exibir": true, "modulos_m": [1.20, 0.51, 0.61]},
        "render": {"motor": "BLENDER_EEVEE_NEXT",
                   "resolucao_x": 1280, "resolucao_y": 960, "amostras": 64},
        "itens": [{"nome": "Cuba G", "formato": "retangulo",
                   "glb": "cuba_g.glb" | null,
                   "x": 0.10, "y": 0.47, "z": 0.90,
                   "largura_m": 0.21, "profundidade_m": 0.53,
                   "altura_m": 0.15, "cor": [0.8, 0.8, 0.8]}]
    }
"""

import glob
import json
import math
import os
import random
import sys
import time
import traceback

import bmesh
import bpy
from mathutils import Vector

MARCADOR_SUCESSO = "[RENDER_3D_OK]"
MARCADOR_ERRO = "[RENDER_3D_ERRO]"

# Marcador usado pelo wrapper (blender_headless.py) para localizar o JSON de
# métricas no stdout, quando a telemetria está ativa.
MARCADOR_METRICAS = "[RENDER_METRICS_JSON]"

# Os modelos .glb (cubas, panelas e comidas) são importados na orientação
# original do arquivo: já vêm modelados "em pé" (abertura/base alinhadas
# aos eixos), portanto NENHUMA correção de rotação é aplicada.

# [Debug] Salva a cena montada em .blend para inspeção manual. Ativo apenas
# com SALVAR_BLEND_DEBUG = true/1/yes (padrão desligado: o save completo da
# cena custa ~1,4 s e não interfere no render final).
RAIZ_PROJETO = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..")
)
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


# ---------------------------------------------------------------------------
# Telemetria opcional (ENABLE_RENDER_METRICS = true/1/yes, case-insensitive)
#
# Quando inativa, nenhuma chamada de timer é feita e nenhum arquivo é criado:
# o fluxo de renderização permanece exatamente o original.
# ---------------------------------------------------------------------------
def _metricas_ativas():
    valor = os.environ.get("ENABLE_RENDER_METRICS", "").strip().lower()
    return valor in ("true", "1", "yes")


METRICAS_ATIVAS = _metricas_ativas()
_INICIO_SCRIPT = time.perf_counter()
METRICAS = {}
_PROCESSO_MONITORADO = None  # psutil.Process usado para CPU (best-effort)
_CPU_INICIO = None  # (wall_clock, cpu_segundos) da medição nativa Win32

CHAVES_METRICAS_TEMPO = (
    "init_sec",
    "balcao_setup_sec",
    "food_allocation_sec",
    "boolean_operations_sec",
    "environment_and_dimensions_sec",
    "eevee_render_sec",
    "file_save_sec",
    "total_script_sec",
)

if METRICAS_ATIVAS:
    METRICAS.update({chave: 0.0 for chave in CHAVES_METRICAS_TEMPO})
    METRICAS["peak_memory_mb"] = 0.0
    METRICAS["cpu_percent"] = 0.0
    METRICAS["render_device"] = None


def _dispositivo_render():
    """Nome do dispositivo de renderização ativo (ex.: 'NVIDIA Corporation |
    NVIDIA GeForce RTX 4060 Ti'). Inicializa o contexto de GPU (best-effort);
    se falhar, retorna None e a métrica fica ausente. É o campo que prova se o
    render rodou em GPU de verdade ou em software (llvmpipe/WARP) num servidor
    sem GPU."""
    try:
        import gpu

        gpu.init()
        return f"{gpu.platform.vendor_get()} | {gpu.platform.renderer_get()}"
    except Exception:
        return None


def _registrar_metrica(chave, inicio):
    """Acumula a duração da fase `chave` em segundos (perf_counter)."""
    if METRICAS_ATIVAS:
        METRICAS[chave] += time.perf_counter() - inicio


def _amostrar_memoria_pico():
    """Mede o pico de RAM (RSS) funcionando nativamente em Windows e Linux,
    sem depender obrigatoriamente do pacote 'psutil' instalado no Blender.
    """
    if not METRICAS_ATIVAS:
        return

    rss_mb = 0.0

    # 1. TENTATIVA COM PSUTIL (Se instalado no Python do Blender)
    try:
        import psutil

        processo = psutil.Process(os.getpid())
        # Inclui a memória de processos filhos criados pelo Blender, se houver
        mem_bytes = processo.memory_info().rss
        for filho in processo.children(recursive=True):
            try:
                mem_bytes += filho.memory_info().rss
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        rss_mb = mem_bytes / (1024.0 * 1024.0)
    except Exception:
        pass

    # 2. FALLBACK PARA WINDOWS (Win32 API nativa via ctypes - Sem instalar nada)
    #
    # IMPORTANTE: ctypes.windll não declara argtypes/restype por padrão, então
    # o HANDLE retornado por GetCurrentProcess era truncado para 32 bits e a
    # chamada GetProcessMemoryInfo falhava (BOOL = 0), mantendo a métrica em
    # 0.0. Aqui as assinaturas são declaradas explicitamente.
    if rss_mb == 0.0 and os.name == "nt":
        try:
            import ctypes
            from ctypes import wintypes

            class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
                _fields_ = [
                    ("cb", wintypes.DWORD),
                    ("PageFaultCount", wintypes.DWORD),
                    ("PeakWorkingSetSize", ctypes.c_size_t),
                    ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t),
                    ("PeakPagefileUsage", ctypes.c_size_t),
                ]

            psapi = ctypes.WinDLL("psapi", use_last_error=True)
            GetProcessMemoryInfo = psapi.GetProcessMemoryInfo
            GetProcessMemoryInfo.argtypes = [
                wintypes.HANDLE,
                ctypes.POINTER(PROCESS_MEMORY_COUNTERS),
                wintypes.DWORD,
            ]
            GetProcessMemoryInfo.restype = wintypes.BOOL

            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            GetCurrentProcess = kernel32.GetCurrentProcess
            GetCurrentProcess.restype = wintypes.HANDLE

            pmc = PROCESS_MEMORY_COUNTERS()
            pmc.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS)
            handle = GetCurrentProcess()

            if GetProcessMemoryInfo(handle, ctypes.byref(pmc), pmc.cb):
                # PeakWorkingSetSize armazena o PICO MÁXIMO de RAM que o processo já atingiu
                rss_mb = pmc.PeakWorkingSetSize / (1024.0 * 1024.0)
        except Exception:
            pass

    # 3. FALLBACK PARA LINUX / POSIX (via módulo 'resource')
    if rss_mb == 0.0:
        try:
            import resource

            pico_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            # No Linux, ru_maxrss é retornado em Kilobytes
            # No macOS (Darwin), é retornado em Bytes
            divisor = 1024.0 if sys.platform != "darwin" else (1024.0 * 1024.0)
            rss_mb = pico_kb / divisor
        except Exception:
            pass

    # 4. FALLBACK FINAL: Memória da cena do próprio Blender (bpy.app.memory)
    if rss_mb == 0.0:
        try:
            # bpy.app.memory.peak_usage() indica o pico de RAM alocado para geometria/shaders
            rss_mb = bpy.app.memory.peak_usage() / (1024.0 * 1024.0)
        except Exception:
            pass

    # Atualiza o pico global armazenado
    if rss_mb > 0.0:
        METRICAS["peak_memory_mb"] = max(METRICAS.get("peak_memory_mb", 0.0), rss_mb)


def _tempo_cpu_processo():
    """Tempo de CPU acumulado do processo (kernel+user) em segundos, sem
    psutil: Win32 GetProcessTimes. Retorna None se indisponível ou falhar
    (não-Windows ou erro)."""
    if os.name != "nt":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        class FILETIME(ctypes.Structure):
            _fields_ = [
                ("dwLowDateTime", wintypes.DWORD),
                ("dwHighDateTime", wintypes.DWORD),
            ]

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        GetProcessTimes = kernel32.GetProcessTimes
        GetProcessTimes.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(FILETIME),
            ctypes.POINTER(FILETIME),
            ctypes.POINTER(FILETIME),
            ctypes.POINTER(FILETIME),
        ]
        GetProcessTimes.restype = wintypes.BOOL
        GetCurrentProcess = kernel32.GetCurrentProcess
        GetCurrentProcess.restype = wintypes.HANDLE

        criacao = FILETIME()
        saida = FILETIME()
        kernel = FILETIME()
        usuario = FILETIME()
        if not GetProcessTimes(
            GetCurrentProcess(),
            ctypes.byref(criacao),
            ctypes.byref(saida),
            ctypes.byref(kernel),
            ctypes.byref(usuario),
        ):
            return None

        def _para_segundos(ft):
            # FILETIME: 100-ns unidades
            return (ft.dwHighDateTime * 4294967296 + ft.dwLowDateTime) / 1.0e7

        return _para_segundos(kernel) + _para_segundos(usuario)
    except Exception:
        return None


def _iniciar_cpu():
    """Prepara a medição de CPU do processo Blender.

    Prefere psutil (funciona em Windows/Linux, mede % sobre um núcleo e pode
    passar de 100% em multi-core); sem psutil, usa a medição nativa Win32
    (GetProcessTimes) entre o início e o fim do render."""
    global _PROCESSO_MONITORADO, _CPU_INICIO
    if not METRICAS_ATIVAS:
        return
    _CPU_INICIO = None
    try:
        import psutil

        _PROCESSO_MONITORADO = psutil.Process(os.getpid())
        _PROCESSO_MONITORADO.cpu_percent(interval=None)
        return
    except Exception:
        _PROCESSO_MONITORADO = None

    inicio_cpu = _tempo_cpu_processo()
    if inicio_cpu is not None:
        _CPU_INICIO = (time.perf_counter(), inicio_cpu)


def _finalizar_cpu():
    """Retorna o % de CPU do processo Blender desde `_iniciar_cpu`."""
    if _PROCESSO_MONITORADO is not None:
        try:
            return _PROCESSO_MONITORADO.cpu_percent(interval=None)
        except Exception:
            return 0.0
    if _CPU_INICIO is None:
        return 0.0
    fim_cpu = _tempo_cpu_processo()
    if fim_cpu is None:
        return 0.0
    parede0, cpu0 = _CPU_INICIO
    parede = time.perf_counter() - parede0
    if parede <= 0.0:
        return 0.0
    # Mesma semântica do psutil: % em relação a UM núcleo (pode passar de 100)
    return round((fim_cpu - cpu0) / parede * 100.0, 1)


# ---------------------------------------------------------------------------
# Entrada de dados
# ---------------------------------------------------------------------------
def ler_argumentos_json():
    """Lê o JSON enviado pela linha de comando (inline ou caminho de arquivo)."""
    argv = sys.argv
    if "--" not in argv:
        raise ValueError(
            "Argumentos ausentes. Use: blender -b -P blender_render_script.py -- <json>"
        )

    argumentos = argv[argv.index("--") + 1 :]
    if not argumentos:
        raise ValueError("Nenhum argumento JSON informado após '--'.")

    bruto = argumentos[0]
    if os.path.exists(bruto):
        with open(bruto, "r", encoding="utf-8") as arquivo:
            return json.load(arquivo)
    return json.loads(bruto)


# ---------------------------------------------------------------------------
# Utilidades de cena
# ---------------------------------------------------------------------------
def criar_material(nome, cor, rugosidade=0.45, metalico=0.0):
    material = bpy.data.materials.get(nome) or bpy.data.materials.new(nome)
    material.use_nodes = True
    bsdf = next(
        (n for n in material.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None
    )
    if bsdf is not None:
        bsdf.inputs["Base Color"].default_value = (*cor, 1.0)
        bsdf.inputs["Roughness"].default_value = rugosidade
        bsdf.inputs["Metallic"].default_value = metalico
    return material


def obter_ou_criar_cubo(nome, localizacao, dimensoes, material=None):
    objeto = bpy.data.objects.get(nome)
    if objeto is None:
        bpy.ops.mesh.primitive_cube_add(size=1.0, location=localizacao)
        objeto = bpy.context.active_object
        objeto.name = nome
    objeto.location = localizacao
    objeto.dimensions = dimensoes
    if material is not None:
        objeto.data.materials.clear()
        objeto.data.materials.append(material)
    return objeto


def _importar_glb(caminho_glb):
    """Importa um .glb e retorna a lista de objetos novos na cena."""
    objetos_antes = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=caminho_glb)
    importados = [o for o in bpy.data.objects if o not in objetos_antes]
    if not importados:
        raise RuntimeError(f"Nenhum objeto importado de '{caminho_glb}'.")
    return importados


# Cache de imports GLB: os .glb (travessas e comidas) são importados UMA única
# vez por arquivo e clonados por item via `_duplicar_hierarquia` (malhas,
# materiais e texturas compartilhados, transform independente). No job típico
# isso reduz de ~48 imports GLTF para ~10 (2 travessas únicas + 8 comidas).
CACHE_GLB = {}


def _desvincular_hierarquia(tops):
    """Desvincula a hierarquia da coleção da cena: os objetos mestres ficam
    apenas como modelo para `_duplicar_hierarquia`, sem renderizar."""
    pilha = list(tops)
    while pilha:
        objeto = pilha.pop()
        for colecao in list(objeto.users_collection):
            colecao.objects.unlink(objeto)
        pilha.extend(objeto.children)


def _importar_glb_cached(caminho_glb):
    """Importa um .glb uma única vez e devolve os topos da hierarquia mestra
    (desvinculada da cena). Chamadas seguintes clonam a hierarquia."""
    registro = CACHE_GLB.get(caminho_glb)
    if registro is not None:
        return registro["tops"]

    importados = _importar_glb(caminho_glb)
    tops = [o for o in importados if o.parent is None]
    _desvincular_hierarquia(tops)
    CACHE_GLB[caminho_glb] = {"tops": tops}
    return tops


def _comida_base_cached(caminho_comida):
    """Importa e normaliza a comida .glb uma única vez: centro da footprint na
    origem e base em Z=0. Retorna (tops, dim_x, dim_y); as chamadas seguintes
    clonam a hierarquia mestra já normalizada."""
    registro = CACHE_GLB.get(caminho_comida)
    if registro is not None:
        return registro["tops"], registro["dim_x"], registro["dim_y"]

    tops = _importar_glb_cached(caminho_comida)
    caixa = _caixa_englobante(tops)
    if caixa is None:
        raise RuntimeError(f"Comida '{caminho_comida}' não contém malhas.")

    (min_x, max_x), (min_y, max_y), (min_z, _) = caixa
    centro_x = (min_x + max_x) / 2.0
    centro_y = (min_y + max_y) / 2.0
    for topo in tops:
        topo.location = (
            topo.location.x - centro_x,
            topo.location.y - centro_y,
            topo.location.z - min_z,
        )

    CACHE_GLB[caminho_comida] = {
        "tops": tops,
        "dim_x": max(max_x - min_x, 1e-6),
        "dim_y": max(max_y - min_y, 1e-6),
    }
    return tops, CACHE_GLB[caminho_comida]["dim_x"], CACHE_GLB[caminho_comida]["dim_y"]


def _remover_objeto(nome):
    """Remove um objeto da cena se existir (ex.: herdado do template)."""
    objeto = bpy.data.objects.get(nome)
    if objeto is not None:
        bpy.data.objects.remove(objeto, do_unlink=True)


def _encontrar_textura(pasta, palavras_chave):
    """Localiza o primeiro arquivo de imagem da pasta cujo nome contenha uma
    das palavras-chave (ex: 'Color', 'NormalGL', 'Roughness', 'Specular')."""
    if not pasta or not os.path.isdir(pasta):
        return None
    for caminho in sorted(glob.glob(os.path.join(pasta, "*"))):
        nome = os.path.basename(caminho).lower()
        if not nome.endswith((".png", ".jpg", ".jpeg")):
            continue
        if any(palavra.lower() in nome for palavra in palavras_chave):
            return caminho
    return None


def _material_pbr(nome, pasta, tiling, cor_fallback):
    """Constrói um material PBR a partir das texturas da pasta, com nó de
    Mapping para repetição (tiling). Detecta dinamicamente mapa de Specular
    (conecta em 'Specular IOR Level') vs Roughness (conecta em 'Roughness')."""
    material = bpy.data.materials.get(nome) or bpy.data.materials.new(nome)
    material.use_nodes = True
    arvore = material.node_tree
    bsdf = next((n for n in arvore.nodes if n.type == "BSDF_PRINCIPLED"), None)
    if bsdf is None:
        return material

    caminho_cor = _encontrar_textura(pasta, ("Color", "Albedo", "Diffuse"))
    if caminho_cor is None:
        print(f" > [Aviso] Sem textura Color em '{pasta}'. Cor chapada aplicada.")
        bsdf.inputs["Base Color"].default_value = (*cor_fallback, 1.0)
        bsdf.inputs["Roughness"].default_value = 0.9
        return material

    tex_coord = arvore.nodes.new("ShaderNodeTexCoord")
    mapping = arvore.nodes.new("ShaderNodeMapping")
    mapping.inputs["Scale"].default_value = (tiling[0], tiling[1], 1.0)
    arvore.links.new(tex_coord.outputs["UV"], mapping.inputs["Vector"])

    def adicionar_textura(caminho, nao_colorido=False):
        textura = arvore.nodes.new("ShaderNodeTexImage")
        textura.image = bpy.data.images.load(caminho)
        if nao_colorido:
            textura.image.colorspace_settings.name = "Non-Color"
        arvore.links.new(mapping.outputs["Vector"], textura.inputs["Vector"])
        return textura

    tex_cor = adicionar_textura(caminho_cor)
    arvore.links.new(tex_cor.outputs["Color"], bsdf.inputs["Base Color"])

    caminho_rough = _encontrar_textura(pasta, ("Roughness",))
    caminho_spec = _encontrar_textura(pasta, ("Specular",))
    if caminho_rough:
        tex_rough = adicionar_textura(caminho_rough, nao_colorido=True)
        arvore.links.new(tex_rough.outputs["Color"], bsdf.inputs["Roughness"])
    elif caminho_spec:
        entrada_spec = bsdf.inputs.get("Specular IOR Level") or bsdf.inputs.get(
            "Specular"
        )
        tex_spec = adicionar_textura(caminho_spec, nao_colorido=True)
        if entrada_spec is not None:
            arvore.links.new(tex_spec.outputs["Color"], entrada_spec)
            print(
                f" > Mapa Specular detectado em '{os.path.basename(caminho_spec)}': "
                "conectado diretamente ao Principled BSDF."
            )

    caminho_normal = _encontrar_textura(pasta, ("NormalGL", "Normal"))
    if caminho_normal:
        tex_normal = adicionar_textura(caminho_normal, nao_colorido=True)
        normal_map = arvore.nodes.new("ShaderNodeNormalMap")
        arvore.links.new(tex_normal.outputs["Color"], normal_map.inputs["Color"])
        arvore.links.new(normal_map.outputs["Normal"], bsdf.inputs["Normal"])

    return material


def configurar_piso(conf_balcao):
    """Piso procedural: plano em Z=0 com material PBR de
    `assets/textures/piso/` (tiling via Mapping). Fallback: cor chapada."""
    # O chão genérico do template cobriria o piso procedural
    _remover_objeto("Chao")
    centro_x = conf_balcao["largura_m"] / 2.0
    centro_y = conf_balcao["profundidade_m"] / 2.0

    lado = 12.0
    material = _material_pbr(
        "MAT_Piso",
        os.path.join(PASTA_TEXTURAS, "piso"),
        tiling=(lado / 2.0, lado / 2.0),  # repetição a cada ~2 m (escala real)
        cor_fallback=(0.42, 0.42, 0.46),
    )
    bpy.ops.mesh.primitive_plane_add(size=lado, location=(centro_x, centro_y, 0.0))
    piso = bpy.context.active_object
    piso.name = "Piso"
    piso.data.materials.append(material)
    return piso


def configurar_parede(conf_balcao):
    """Parede de fundo procedural: plano vertical com material PBR de
    `assets/textures/parede/` (mapa Specular detectado dinamicamente).
    Fallback: cor chapada."""
    largura = conf_balcao["largura_m"]
    profundidade = conf_balcao["profundidade_m"]
    centro_x = largura / 2.0
    y_parede = profundidade + 0.8
    largura_parede = max(largura * 1.5, 4.0)
    altura_parede = 3.0

    material = _material_pbr(
        "MAT_Parede",
        os.path.join(PASTA_TEXTURAS, "parede"),
        tiling=(largura_parede / 2.0, altura_parede / 2.0),
        cor_fallback=(0.88, 0.87, 0.85),
    )
    bpy.ops.mesh.primitive_plane_add(
        size=2.0,
        location=(centro_x, y_parede, altura_parede / 2.0),
        rotation=(math.radians(90.0), 0.0, 0.0),
    )
    parede = bpy.context.active_object
    parede.name = "Parede"
    parede.scale = (largura_parede / 2.0, altura_parede / 2.0, 1.0)
    parede.data.materials.append(material)
    return parede


def _configurar_balcao_glb(conf_balcao, caminho_glb):
    """Balcão paramétrico: importa `balcao.glb` e redimensiona X (largura) e
    Y (profundidade) para casar exatamente com o payload. Retorna o Z do tampo
    (face superior da mesa escalada), referência para o Z das travessas."""
    print(f" > Importando balcão paramétrico: {caminho_glb}")
    # Balcão genérico do template conflitaria com o modelo importado
    _remover_objeto("Balcao_Corpo")
    _remover_objeto("Balcao_Tampo")
    importados = _importar_glb(caminho_glb)
    raiz = bpy.data.objects.new("Balcao", None)
    bpy.context.scene.collection.objects.link(raiz)
    for objeto in importados:
        if objeto.parent is None:
            objeto.parent = raiz

    caixa = _caixa_englobante(importados)
    (min_x, max_x), (min_y, max_y), (min_z, max_z) = caixa
    dim_x = max(max_x - min_x, 1e-6)
    dim_y = max(max_y - min_y, 1e-6)

    escala_x = conf_balcao["largura_m"] / dim_x
    escala_y = conf_balcao["profundidade_m"] / dim_y
    raiz.scale = (escala_x, escala_y, 1.0)  # Z preserva a altura original do modelo

    raiz.location = (-min_x * escala_x, -min_y * escala_y, -min_z)

    z_tampo = max_z  # escala Z = 1
    print(
        f" > Balcão GLB: bbox {dim_x:.3f}x{dim_y:.3f}x{max_z - min_z:.3f} m -> "
        f"alvo {conf_balcao['largura_m']:.3f}x{conf_balcao['profundidade_m']:.3f} m | "
        f"tampo em Z={z_tampo:.3f} m"
    )
    return z_tampo


def _configurar_balcao_procedural(conf_balcao):
    """Fallback sem balcao.glb: corpo + tampo em cubos. Retorna o Z do tampo."""
    largura = conf_balcao["largura_m"]
    profundidade = conf_balcao["profundidade_m"]
    altura = conf_balcao["altura_m"]
    espessura_tampo = conf_balcao.get("espessura_tampo_m", 0.05)

    print(" > [Aviso] balcao.glb não encontrado. Usando balcão procedural.")
    mat_corpo = criar_material(
        "MAT_Balcao_Corpo", (0.24, 0.25, 0.26), rugosidade=0.4, metalico=0.6
    )
    mat_tampo = criar_material(
        "MAT_Balcao_Tampo", (0.62, 0.63, 0.65), rugosidade=0.3, metalico=0.6
    )

    altura_corpo = max(altura - espessura_tampo, 0.01)
    obter_ou_criar_cubo(
        "Balcao_Corpo",
        localizacao=(largura / 2.0, profundidade / 2.0, altura_corpo / 2.0),
        dimensoes=(largura, profundidade, altura_corpo),
        material=mat_corpo,
    )
    obter_ou_criar_cubo(
        "Balcao_Tampo",
        localizacao=(
            largura / 2.0,
            profundidade / 2.0,
            altura - espessura_tampo / 2.0,
        ),
        dimensoes=(largura + 0.04, profundidade + 0.04, espessura_tampo),
        material=mat_tampo,
    )
    return altura


def configurar_balcao(conf_balcao, glb_dir):
    """Monta o balcão (GLB paramétrico ou procedural) e retorna o Z do tampo."""
    candidato = os.path.join(glb_dir, GLB_BALCAO) if glb_dir else None
    if candidato and os.path.exists(candidato):
        return _configurar_balcao_glb(conf_balcao, candidato)
    return _configurar_balcao_procedural(conf_balcao)


def configurar_camera(conf_camera, conf_balcao):
    """Posiciona a câmera 'por cima', no ângulo de elevação configurado (75°)."""
    largura = conf_balcao["largura_m"]
    profundidade = conf_balcao["profundidade_m"]
    altura = conf_balcao["altura_m"]

    angulo = math.radians(conf_camera.get("angulo_elevacao_graus", 75.0))
    margem = conf_camera.get("fator_margem", 1.3)

    alvo = Vector((largura / 2.0, profundidade / 2.0, altura))

    camera = bpy.data.objects.get("Camera")
    if camera is None:
        dados_camera = bpy.data.cameras.new("Camera")
        camera = bpy.data.objects.new("Camera", dados_camera)
        bpy.context.scene.collection.objects.link(camera)
    bpy.context.scene.camera = camera

    # Distância calculada para enquadrar a maior dimensão do balcão com margem
    lente_mm = conf_camera.get("lente_mm", 50.0)
    camera.data.lens = lente_mm
    sensor_mm = camera.data.sensor_width  # padrão 36mm
    fov_horizontal = 2.0 * math.atan((sensor_mm / 2.0) / lente_mm)
    maior_dimensao = max(largura, profundidade)
    distancia = ((maior_dimensao / 2.0) * margem) / math.tan(fov_horizontal / 2.0)

    deslocamento = Vector(
        (0.0, -distancia * math.cos(angulo), distancia * math.sin(angulo))
    )
    camera.location = alvo + deslocamento
    camera.rotation_euler = (alvo - camera.location).to_track_quat("-Z", "Y").to_euler()
    return camera


# Fotografia de alimentos: cor quente das luzes principais (~3400 K, tom
# amarelado de restaurante) e intensidade do HDRI de ambiente. Strength 1.0
# calibrado para não estourar os brancos (acima disso o cowboy_town_saloon
# _2k.exr satura a cena). TOM_HDRI multiplica o fundo por um tom levemente
# amarelado para evitar iluminação fria de fundo.
COR_LUZ_QUENTE = (1.0, 0.82, 0.65)
INTENSIDADE_HDRI = 1.0
TOM_HDRI = (1.0, 0.95, 0.88)
SATURACAO_HDRI = 0.85


def _encontrar_hdri():
    """Localiza dinamicamente o primeiro arquivo `.hdr`/`.exr` das pastas de
    HDRI (`assets/textures/hdri/` com fallback para `assets/hdri/`)."""
    for pasta in PASTAS_HDRI:
        if not os.path.isdir(pasta):
            continue
        for caminho in sorted(glob.glob(os.path.join(pasta, "*"))):
            if caminho.lower().endswith((".hdr", ".exr")):
                return caminho
    return None


def _criar_multiply_color(arvore, cor_constante):
    """Cria um nó de mistura MULTIPLY com o segundo operando fixo (cor
    constante). Aceita o `ShaderNodeMix` (RGBA) do Blender 4.x/5.x e o
    `ShaderNodeMixRGB` legado. Retorna (nó, nome_socket_entrada, nome_
    socket_saida) para o chamador linkar o primeiro operando (HDRI) e a saída."""
    if hasattr(bpy.types, "ShaderNodeMix"):
        no = arvore.nodes.new("ShaderNodeMix")
        no.data_type = "RGBA"
        no.blend_type = "MULTIPLY"
        entrada = "A_Color" if "A_Color" in no.inputs else "A"
        saida = "Result_Color" if "Result_Color" in no.outputs else "Result"
        fator = "Factor_Color" if "Factor_Color" in no.inputs else "Factor"
        no.inputs[fator].default_value = 1.0
        no.inputs["B_Color" if "B_Color" in no.inputs else "B"].default_value = (
            *cor_constante,
            1.0,
        )
        return no, entrada, saida
    no = arvore.nodes.new("ShaderNodeMixRGB")
    no.blend_type = "MULTIPLY"
    no.inputs["Fac"].default_value = 1.0
    no.inputs["Color2"].default_value = (*cor_constante, 1.0)
    return no, "Color1", "Color"


def _configurar_mundo_hdri(caminho_hdri):
    """Conecta o HDRI ao `World.node_tree` via `ShaderNodeTexEnvironment`
    (Background com Strength 1.0), com cadeia de aquecimento:
    Environment Texture -> Hue/Saturation/Value (Hue 0.5, Saturation 0.85)
    -> MULTIPLY (tom amarelado 1.0, 0.95, 0.88) -> Background."""
    mundo = bpy.context.scene.world
    if mundo is None:
        mundo = bpy.data.worlds.new("Mundo")
        bpy.context.scene.world = mundo
    mundo.use_nodes = True
    arvore = mundo.node_tree
    for no in list(arvore.nodes):
        if no.type not in ("BACKGROUND", "OUTPUT_WORLD"):
            arvore.nodes.remove(no)
    fundo = next((n for n in arvore.nodes if n.type == "BACKGROUND"), None)
    if fundo is None:
        fundo = arvore.nodes.new("ShaderNodeBackground")
    saida = next((n for n in arvore.nodes if n.type == "OUTPUT_WORLD"), None)
    if saida is None:
        saida = arvore.nodes.new("ShaderNodeOutputWorld")

    ambiente = arvore.nodes.new("ShaderNodeTexEnvironment")
    ambiente.image = bpy.data.images.load(caminho_hdri)

    # Hue/Saturation/Value: Hue 0.5 preserva a matriz, Saturation levemente
    # reduzida para suavizar cores agressivas do fundo.
    hsv = arvore.nodes.new("ShaderNodeHueSaturation")
    hsv.inputs["Hue"].default_value = 0.5
    hsv.inputs["Saturation"].default_value = SATURACAO_HDRI
    hsv.inputs["Value"].default_value = 1.0
    arvore.links.new(ambiente.outputs["Color"], hsv.inputs["Color"])

    # Tom amarelado (multiplicação) para evitar fundo frio.
    multiplicador, entrada_a, saida_result = _criar_multiply_color(arvore, TOM_HDRI)
    arvore.links.new(hsv.outputs["Color"], multiplicador.inputs[entrada_a])
    arvore.links.new(multiplicador.outputs[saida_result], fundo.inputs["Color"])
    fundo.inputs["Strength"].default_value = INTENSIDADE_HDRI
    arvore.links.new(fundo.outputs["Background"], saida.inputs["Surface"])


def _criar_area_light(nome, posicao, alvo, energia, size_x, size_y, angulo_graus=45.0):
    """Area light RECTANGLE na posição dada, com cor quente de fotografia de
    alimentos. Aponta para o alvo com elevação fixa de ~45° em relação ao
    tampo (evita iluminação 100% vertical de topo). Luzes grandes e suaves
    não queimam alimentos claros (arroz/batata)."""
    objeto = bpy.data.objects.get(nome)
    if objeto is None:
        dados_luz = bpy.data.lights.new(nome, type="AREA")
        objeto = bpy.data.objects.new(nome, dados_luz)
        bpy.context.scene.collection.objects.link(objeto)
    objeto.data.color = COR_LUZ_QUENTE
    objeto.data.energy = energia
    # RECTANGLE: no Blender 4.x o tamanho é size_x/size_y; no 5.x o size é a
    # largura (X) e size_y a altura (Y).
    try:
        objeto.data.shape = "RECTANGLE"
    except TypeError:
        pass
    if hasattr(objeto.data, "size_x"):
        objeto.data.size_x = size_x
        objeto.data.size_y = size_y
    else:
        objeto.data.size = size_x
        objeto.data.size_y = size_y
    objeto.location = posicao

    # Direção horizontal para o alvo + elevação fixa de `angulo_graus`
    horizontal = Vector((alvo[0], alvo[1], 0.0)) - Vector((posicao[0], posicao[1], 0.0))
    horizontal.z = 0.0
    if horizontal.length_squared < 1e-9:
        horizontal = Vector((1.0, 0.0, 0.0))
    else:
        horizontal.normalize()
    angulo = math.radians(angulo_graus)
    direcao = Vector(
        (
            horizontal.x * math.cos(angulo),
            horizontal.y * math.cos(angulo),
            -math.sin(angulo),
        )
    )
    objeto.rotation_euler = direcao.to_track_quat("-Z", "Y").to_euler()
    return objeto


def configurar_iluminacao(conf_balcao):
    """Iluminação de estúdio/restaurante (food photography): World HDRI
    dinâmico + 2 area lights quentes (~3800 K) acima e levemente inclinadas
    sobre o balcão. Substitui a luz solar plana do template."""
    # A luz solar chapada (flat light) do template dá lugar ao conjunto
    # HDRI + area lights quentes.
    _remover_objeto("Sol")

    caminho_hdri = _encontrar_hdri()
    if caminho_hdri:
        _configurar_mundo_hdri(caminho_hdri)
        print(
            f" > World HDRI carregado: {os.path.basename(caminho_hdri)} "
            f"(Strength {INTENSIDADE_HDRI})"
        )
    else:
        mundo = bpy.context.scene.world
        if mundo is None:
            mundo = bpy.data.worlds.new("Mundo")
            bpy.context.scene.world = mundo
        mundo.use_nodes = True
        fundo = mundo.node_tree.nodes.get("Background")
        if fundo is not None:
            fundo.inputs["Color"].default_value = (0.85, 0.87, 0.92, 1.0)
            fundo.inputs["Strength"].default_value = 0.35
        print(
            " > [Aviso] Nenhum HDRI (.hdr/.exr) encontrado em "
            "assets/textures/hdri/. Usando fundo chapado como fallback."
        )

    largura = conf_balcao["largura_m"]
    profundidade = conf_balcao["profundidade_m"]
    altura = conf_balcao["altura_m"]
    centro_balcao = (largura / 2.0, profundidade / 2.0, altura)

    # Luz chave: à frente/esquerda, acima e inclinada a 45° sobre o balcão;
    # luz de preenchimento: atrás/direita, mais suave e difusa. Luzes
    # RECTANGLE grandes e de baixa potência não queimam alimentos claros.
    _criar_area_light(
        "Luz_Chave",
        (largura * 0.25, -0.60, altura + 1.10),
        centro_balcao,
        energia=80.0,
        size_x=2.0,
        size_y=1.0,
    )
    _criar_area_light(
        "Luz_Preenchimento",
        (largura * 0.75, profundidade + 0.60, altura + 1.40),
        centro_balcao,
        energia=35.0,
        size_x=1.5,
        size_y=0.8,
    )


def carregar_cenario(template_path):
    """Carrega o template .blend se existir; senão parte de uma cena vazia."""
    if template_path and os.path.exists(template_path):
        print(f" > Carregando template de cenário: {template_path}")
        bpy.ops.wm.open_mainfile(filepath=template_path)
    else:
        print(
            " > [Aviso] Template .blend não encontrado. "
            "Montando cenário procedural padrão."
        )
        bpy.ops.wm.read_factory_settings(use_empty=True)


# ---------------------------------------------------------------------------
# Travessas (itens)
# ---------------------------------------------------------------------------
def _cor_do_item(item, indice):
    cor = item.get("cor")
    if cor and len(cor) == 3:
        return tuple(cor)
    return PALETA_PADRAO[indice % len(PALETA_PADRAO)]


def _aplicar_material(objeto, material):
    if objeto.type == "MESH":
        objeto.data.materials.clear()
        objeto.data.materials.append(material)
    for filho in objeto.children:
        _aplicar_material(filho, material)


def criar_travessa_procedural(item, material):
    """Fallback quando não existe .glb: cilindro (redonda) ou caixa (cuba)."""
    nome = item["nome"]
    x, y, z = item["x"], item["y"], item["z"]
    altura = item.get("altura_m", 0.15)
    largura = item["largura_m"]
    profundidade = item["profundidade_m"]

    if item.get("formato") == "circulo":
        bpy.ops.mesh.primitive_cylinder_add(
            radius=largura / 2.0,
            depth=altura,
            vertices=48,
            location=(x, y, z + altura / 2.0),
        )
    else:
        bpy.ops.mesh.primitive_cube_add(size=1.0, location=(x, y, z + altura / 2.0))
        bpy.context.active_object.dimensions = (largura, profundidade, altura)

    objeto = bpy.context.active_object
    objeto.name = f"ITEM_{nome}"
    _aplicar_material(objeto, material)
    # Peça procedural é sólida: a comida assenta sobre a face superior
    item["z_fundo_interno"] = z + altura
    return objeto


def _caixa_englobante(objetos):
    """Bounding box mundial combinada de uma lista de objetos de malha."""
    pontos = []
    for objeto in objetos:
        if objeto.type != "MESH":
            continue
        pontos.extend(
            [objeto.matrix_world @ Vector(canto) for canto in objeto.bound_box]
        )
    if not pontos:
        return None
    xs = [p.x for p in pontos]
    ys = [p.y for p in pontos]
    zs = [p.z for p in pontos]
    return (min(xs), max(xs)), (min(ys), max(ys)), (min(zs), max(zs))


def _medir_z_fundo_interno(objetos):
    """Estima o Z do fundo interno do recipiente (superfície que a comida deve
    cobrir): percentil 95 dos vértices na região central (30%) da footprint.
    O percentil alto evita confundir a face EXTERNA do fundo (base/pés da
    peça) com a face interna da cavidade. Retorna None se não houver
    vértices suficientes.

    Vectorizado com numpy (embutido no Python do Blender): a transformação
    de todos os vértices vira uma única multiplicação de matrizes em lote,
    em vez de um loop Python por vértice. Fallback em Python puro se o
    numpy não estiver disponível (mesmo algoritmo original)."""
    try:
        import numpy as np
    except ImportError:
        np = None

    if np is not None:
        xs = []
        ys = []
        zs = []
        for objeto in objetos:
            if objeto.type != "MESH" or not objeto.data.vertices:
                continue
            coords = np.empty((len(objeto.data.vertices), 3), dtype=np.float64)
            objeto.data.vertices.foreach_get("co", coords.ravel())
            trans = np.array(objeto.matrix_world)[:3, :]
            mundo = coords @ trans[:, :3].T + trans[:, 3]
            xs.append(mundo[:, 0])
            ys.append(mundo[:, 1])
            zs.append(mundo[:, 2])
        if not xs:
            return None
        px = np.concatenate(xs)
        py = np.concatenate(ys)
        pz = np.concatenate(zs)
        centro_x = (px.min() + px.max()) / 2.0
        centro_y = (py.min() + py.max()) / 2.0
        raio_x = (px.max() - px.min()) * 0.15
        raio_y = (py.max() - py.min()) * 0.15
        mascara = (np.abs(px - centro_x) < raio_x) & (np.abs(py - centro_y) < raio_y)
        z_centrais = np.sort(pz[mascara])
        if z_centrais.size == 0:
            return None
        return float(z_centrais[int(z_centrais.size * 0.95)])

    # Fallback: mesmo algoritmo original em Python puro
    pontos = []
    for objeto in objetos:
        if objeto.type == "MESH":
            pontos.extend(objeto.matrix_world @ v.co for v in objeto.data.vertices)
    if not pontos:
        return None
    xs = [p.x for p in pontos]
    ys = [p.y for p in pontos]
    centro_x = (min(xs) + max(xs)) / 2.0
    centro_y = (min(ys) + max(ys)) / 2.0
    raio_x = (max(xs) - min(xs)) * 0.15
    raio_y = (max(ys) - min(ys)) * 0.15
    z_centrais = sorted(
        p.z
        for p in pontos
        if abs(p.x - centro_x) < raio_x and abs(p.y - centro_y) < raio_y
    )
    if not z_centrais:
        return None
    return z_centrais[int(len(z_centrais) * 0.95)]


def importar_travessa_glb(item, caminho_glb, material_fallback):
    """Importa o .glb na orientação original do arquivo e aplica posição/escala
    para casar com a footprint do layout.

    O arquivo é importado UMA única vez (cache) e clonado por item via
    `_duplicar_hierarquia`: malhas e texturas compartilhadas, transform
    independente (no job típico, 24 travessas usam apenas 2 arquivos únicos).

    Os materiais/texturas originais do .glb são preservados; o material de
    fallback (cor chapada) só é aplicado em malhas importadas sem material
    (copiando a malha, pois as cópias compartilham o mesh mestre).
    """
    tops_mestres = _importar_glb_cached(caminho_glb)
    importados = _duplicar_hierarquia(tops_mestres)

    raiz = bpy.data.objects.new(f"ITEM_{item['nome']}", None)
    bpy.context.scene.collection.objects.link(raiz)
    for objeto in importados:
        if objeto.parent is None:
            objeto.parent = raiz

    caixa = _caixa_englobante(importados)
    if caixa is None:
        raise RuntimeError(f"Arquivo '{caminho_glb}' não contém malhas.")

    (min_x, max_x), (min_y, max_y), (min_z, max_z) = caixa
    dim_x = max(max_x - min_x, 1e-6)
    dim_y = max(max_y - min_y, 1e-6)
    dim_z = max(max_z - min_z, 1e-6)

    escala_x = item["largura_m"] / dim_x
    escala_y = item["profundidade_m"] / dim_y
    escala_z = item.get("altura_m", 0.15) / dim_z

    print(
        f" > '{item['nome']}': bbox glb {dim_x:.3f}x{dim_y:.3f}x{dim_z:.3f} m -> "
        f"alvo {item['largura_m']:.3f}x{item['profundidade_m']:.3f}x"
        f"{item.get('altura_m', 0.15):.3f} m | "
        f"escala ({escala_x:.3f}, {escala_y:.3f}, {escala_z:.3f})"
    )

    raiz.scale = (escala_x, escala_y, escala_z)

    centro_x = (min_x + max_x) / 2.0
    centro_y = (min_y + max_y) / 2.0
    raiz.location = (
        item["x"] - centro_x * escala_x,
        item["y"] - centro_y * escala_y,
        item["z"] - min_z * escala_z,  # base da peça apoiada sobre o tampo
    )

    # Preserva as texturas originais do .glb: a cor chapada só serve de
    # fallback para malhas que vieram sem nenhum material. A malha é copiada
    # quando compartilhada, para não alterar a hierarquia mestra nem as
    # cópias de outros itens.
    for objeto in importados:
        if objeto.type == "MESH" and not objeto.data.materials:
            if objeto.data.users > 1:
                objeto.data = objeto.data.copy()
            _aplicar_material(objeto, material_fallback)

    # Mede o fundo interno real do recipiente para assentar a comida sobre ele
    bpy.context.view_layer.update()
    z_fundo = _medir_z_fundo_interno(importados)
    if z_fundo is not None:
        item["z_fundo_interno"] = z_fundo
        print(f" > '{item['nome']}': fundo interno medido em Z={z_fundo:.3f} m")
    return raiz


def posicionar_itens(itens, glb_dir, z_tampo, deck_comidas=None):
    for indice, item in enumerate(itens):
        # As travessas sempre apoiam no topo do tampo da mesa escalada,
        # independentemente do Z vindo no JSON.
        item["z"] = z_tampo
        material = criar_material(
            f"MAT_Item_{indice:03d}", _cor_do_item(item, indice), rugosidade=0.4
        )

        caminho_glb = None
        if item.get("glb") and glb_dir:
            candidato = os.path.join(glb_dir, item["glb"])
            if os.path.exists(candidato):
                caminho_glb = candidato

        if caminho_glb:
            print(f" > Importando GLB para '{item['nome']}': {caminho_glb}")
            importar_travessa_glb(item, caminho_glb, material)
        else:
            if item.get("glb"):
                print(
                    f" > [Aviso] GLB '{item['glb']}' não encontrado para "
                    f"'{item['nome']}'. Usando malha procedural."
                )
            criar_travessa_procedural(item, material)

        if deck_comidas is not None:
            caminho_comida = deck_comidas.sortear(item.get("formato", "retangulo"))
            if caminho_comida:
                posicionar_comida(item, caminho_comida, z_tampo)


# ---------------------------------------------------------------------------
# Comidas (deck sem repetição + encaixe na boca do recipiente)
# ---------------------------------------------------------------------------
class FoodDeckManager:
    """Sorteia .glb de comidas sem repetição (baralho/bag): quando o ciclo
    esgota, o baralho é reembaralhado. Recipientes circulares (`formato ==
    "circulo"`) sorteiam estritamente entre arroz/feijao/macarrao."""

    COMIDAS_CIRCULO = ("arroz.glb", "feijao.glb", "macarrao.glb")

    def __init__(self, comidas_dir):
        self.comidas_dir = comidas_dir
        todos = (
            sorted(glob.glob(os.path.join(comidas_dir, "*.glb"))) if comidas_dir else []
        )
        self._piscina_retangulo = list(todos)
        permitidas = set(self.COMIDAS_CIRCULO)
        self._piscina_circulo = [
            p for p in todos if os.path.basename(p).lower() in permitidas
        ]
        self._baralhos = {"retangulo": [], "circulo": []}
        if not self._piscina_retangulo:
            print(
                f" > [Aviso] Nenhuma comida .glb em '{comidas_dir}'. "
                "Recipientes ficarão vazios."
            )

    def sortear(self, formato):
        chave = "circulo" if formato == "circulo" else "retangulo"
        piscina = (
            self._piscina_circulo if chave == "circulo" else self._piscina_retangulo
        )
        if not piscina:
            if chave == "circulo":
                print(
                    " > [Aviso] Nenhuma comida circular disponível "
                    "(arroz/feijao/macarrao). Panela ficará vazia."
                )
            return None
        baralho = self._baralhos[chave]
        if not baralho:
            baralho = list(piscina)
            random.shuffle(baralho)
            self._baralhos[chave] = baralho
        return baralho.pop()


def _duplicar_hierarquia(objetos_top):
    """Duplica uma hierarquia de objetos (instâncias leves: malha e materiais
    compartilhados, transform independente). Retorna os topos das cópias."""
    mapa = {}
    pilha = list(objetos_top)
    while pilha:
        original = pilha.pop()
        copia = original.copy()
        copia.parent = None
        bpy.context.scene.collection.objects.link(copia)
        mapa[original] = copia
        pilha.extend(original.children)
    for original, copia in mapa.items():
        if original.parent in mapa:
            copia.parent = mapa[original.parent]
    return [mapa[o] for o in objetos_top]


def _montar_instancia_comida(tops, nome, sufixo, posicao, rotacao_z_graus, escala):
    """Ancora as cópias em um empty e aplica posição/rotação Z/escala.
    A escala é aplicada por eixo ANTES da rotação (R @ S), portanto não há
    cisalhamento; escala negativa em X/Y é usada para espelhamento
    (anti-tiling)."""
    raiz = bpy.data.objects.new(f"COMIDA_{nome}_{sufixo}", None)
    bpy.context.scene.collection.objects.link(raiz)
    for topo in tops:
        topo.parent = raiz
    raiz.rotation_euler = (0.0, 0.0, math.radians(rotacao_z_graus))
    raiz.scale = (escala, escala, escala) if not isinstance(escala, tuple) else escala
    raiz.location = posicao
    return raiz


def _coletar_malhas(raizes):
    """Reúne todas as malhas (recursivo) da hierarquia das instâncias."""
    malhas = []
    pilha = list(raizes)
    while pilha:
        objeto = pilha.pop()
        if objeto.type == "MESH":
            malhas.append(objeto)
        pilha.extend(objeto.children)
    return malhas


def _aparar_via_bmesh(raizes, item, circular=False):
    """Apara o que vaza das bordas do recipiente removendo os VÉRTICES
    (bmesh) fora da área útil: toda face com um vértice fora é eliminada,
    garantindo spill zero e borda limpa.

    - Retangular: vértices com |dx| > meia_x OU |dy| > meia_y (boca útil 88%).
    - Circular: vértices além do RAIO INTERNO da panela (distância radial em
      XY). O raio usado é metade da abertura útil (0,44 x largura), que
      coincide com a borda interna do panela_30.glb (medida ~0,436-0,447 x
      largura). Como a comida foi over-scaled em XY antes do corte, o aparo
      apenas recorta o excesso já encostado na parede interna — sem frestas.

    Não usa Boolean (malhas do Tripo são não-manifold, o solver as esvazia
    e o corte custa segundos por peça) nem bake (preserva as normais
    originais da malha). Determinístico e rápido.
    O view_layer.update() é agrupado POR ITEM (uma única reavaliação do
    Dependency Graph antes do corte), e não por célula da grade."""
    abertura_x = item["largura_m"] * FATOR_BOCA_COMIDA
    abertura_y = item["profundidade_m"] * FATOR_BOCA_COMIDA
    meia_x = abertura_x / 2.0
    meia_y = abertura_y / 2.0
    raio2 = meia_x * meia_x
    cx = item["x"]
    cy = item["y"]

    malhas = _coletar_malhas(raizes)
    if not malhas:
        return

    bpy.context.view_layer.update()
    for malha in malhas:
        if malha.data.users > 1:
            malha.data = malha.data.copy()  # copias da grade compartilham o mesh
        mundo = malha.matrix_world
        bm = bmesh.new()
        bm.from_mesh(malha.data)
        bm.verts.ensure_lookup_table()
        fora = []
        for v in bm.verts:
            p = mundo @ v.co
            if circular:
                dx = p.x - cx
                dy = p.y - cy
                if dx * dx + dy * dy > raio2:
                    fora.append(v)
            elif abs(p.x - cx) > meia_x or abs(p.y - cy) > meia_y:
                fora.append(v)
        if fora:
            bmesh.ops.delete(bm, geom=fora, context="VERTS")
        # remove vértices soltos deixados pelo corte
        soltos = [v for v in bm.verts if not v.link_faces]
        if soltos:
            bmesh.ops.delete(bm, geom=soltos, context="VERTS")
        bm.to_mesh(malha.data)
        bm.free()
        malha.data.update()


def posicionar_comida(item, caminho_comida, z_tampo):
    """Importa a comida e preenche a boca do recipiente EXCLUSIVAMENTE com as
    instâncias da malha 3D da comida (sem geometria extra de fundo/massa).

    - Retângulo: grade N x M densa (células ~10 cm, mínimo 2x2), escala por
      eixo preenchendo cada célula (eixos trocados nas rotações de 90/270°,
      sem cisalhamento), rotação Z aleatória (0/90/180/270°), espelhamento
      aleatório em X/Y (50% das células), variação de escala ±2%, overlap
      1.40 e jitter Z simétrico ±2-5 mm (anti-tiling). O que vaza das bordas
      retangulares é aparado removendo as faces fora da boca útil (bmesh,
      sem Boolean).
    - Círculo: peça única centralizada, com over-scaling intencional de ~12%
      no plano XY antes do aparo radial na borda interna da panela (bmesh
      por raio, sem Boolean), garantindo cobertura total sem frestas.
    A comida assenta sobre o fundo interno medido do recipiente (cavidade),
    ficando logo abaixo da borda superior.
    O .glb da comida é importado e normalizado uma única vez (cache) e clonado
    por item/célula: 24 comidas usam apenas ~8 arquivos únicos."""
    print(f" > Comida para '{item['nome']}': {os.path.basename(caminho_comida)}")
    tops, dim_x, dim_y = _comida_base_cached(caminho_comida)

    # Assenta na cavidade interna (fundo medido; fallback: face superior)
    z_base = item.get("z_fundo_interno", z_tampo + item.get("altura_m", 0.15)) + 0.005

    abertura_x = item["largura_m"] * FATOR_BOCA_COMIDA
    abertura_y = item["profundidade_m"] * FATOR_BOCA_COMIDA

    if item.get("formato") == "circulo":
        alvos = _duplicar_hierarquia(tops)
        # Anti-folga: over-scaling intencional no plano XY antes do aparo
        # radial — a malha ultrapassa a parede interna da panela e o corte
        # (raio = abertura útil = borda interna) garante cobertura total.
        # O eixo Z mantém a proporção de altura (não expande em Z).
        _montar_instancia_comida(
            alvos,
            item["nome"],
            "0",
            posicao=(item["x"], item["y"], z_base),
            rotacao_z_graus=0.0,
            escala=(
                (abertura_x / dim_x) * FATOR_EXPANSAO_CIRCULAR,
                (abertura_y / dim_y) * FATOR_EXPANSAO_CIRCULAR,
                abertura_x / dim_x,
            ),
        )
        # Apara o excesso na borda circular interna (bmesh por raio, sem
        # Boolean). A malha foi centralizada na origem pelo cache antes da
        # expansão e a instância é ancorada em (item.x, item.y): o corte fica
        # rigorosamente simétrico ao centro da panela.
        _aparar_via_bmesh(alvos, item, circular=True)
        return

    # Grade densa: células de ~10 cm, sempre >= 2 colunas e 2 linhas
    qtd_x = max(2, int(abertura_x / CELULA_COMIDA_M + 0.5))
    qtd_y = max(2, int(abertura_y / CELULA_COMIDA_M + 0.5))
    celula_x = abertura_x / qtd_x
    celula_y = abertura_y / qtd_y
    print(
        f" > Grade de comida '{item['nome']}': {qtd_x}x{qtd_y} cópias "
        f"(célula {celula_x:.3f}x{celula_y:.3f} m)"
    )

    raizes_borda = []
    for i in range(qtd_x):
        for j in range(qtd_y):
            offset_x = (i + 0.5) * celula_x - abertura_x / 2.0
            offset_y = (j + 0.5) * celula_y - abertura_y / 2.0
            alvos = _duplicar_hierarquia(tops)
            rotacao = random.choice((0.0, 90.0, 180.0, 270.0))
            fator = random.uniform(
                1.0 - VARIACAO_ESCALA_COMIDA, 1.0 + VARIACAO_ESCALA_COMIDA
            )
            fator *= FATOR_TRANSBORDO_CELULA  # folhas transbordam a célula
            # Anti-tiling: jitter Z simétrico (±2 a 5 mm) quebra o vale
            # coplanar entre instâncias vizinhas sem superfícies planas
            jitter_z = random.choice((-1.0, 1.0)) * random.uniform(
                JITTER_Z_MIN_COMIDA_M, JITTER_Z_MAX_COMIDA_M
            )
            # Anti-tiling: espelhamento aleatório em X ou Y (50% das células)
            eixo_espelho = None
            if random.random() < 0.5:
                eixo_espelho = random.choice(("x", "y"))
            # Escala por eixo preenchendo a célula; nas rotações de 90/270°
            # os eixos do modelo trocam (R @ S: escala local, depois gira)
            if rotacao in (90.0, 270.0):
                escala_local_x = celula_y / dim_x
                escala_local_y = celula_x / dim_y
            else:
                escala_local_x = celula_x / dim_x
                escala_local_y = celula_y / dim_y
            # O espelhamento inverte o sinal da escala no eixo sorteado; a
            # escala vertical (Z) usa o módulo para nunca virar a comida
            if eixo_espelho == "x":
                escala_local_x = -escala_local_x
            elif eixo_espelho == "y":
                escala_local_y = -escala_local_y
            raiz = _montar_instancia_comida(
                alvos,
                item["nome"],
                f"{i}_{j}",
                posicao=(
                    item["x"] + offset_x,
                    item["y"] + offset_y,
                    z_base + jitter_z,
                ),
                rotacao_z_graus=rotacao,
                escala=(
                    escala_local_x * fator,
                    escala_local_y * fator,
                    abs(escala_local_x) * fator,
                ),
            )
            # Células totalmente interiores não tocam as bordas da abertura
            # e dispensam o aparo: pula o bmesh (só as células de borda gastam)
            interior_x = (
                abs(offset_x) + (celula_x * FATOR_TRANSBORDO_CELULA) / 2.0
                <= abertura_x / 2.0
            )
            interior_y = (
                abs(offset_y) + (celula_y * FATOR_TRANSBORDO_CELULA) / 2.0
                <= abertura_y / 2.0
            )
            if not (interior_x and interior_y):
                raizes_borda.append(raiz)

    # Apara o que vaza para fora das bordas retangulares da cuba
    if raizes_borda:
        _aparar_via_bmesh(raizes_borda, item)


# ---------------------------------------------------------------------------
# Cotas dimensionais (linhas CURVE + textos FONT virados para a câmera)
# ---------------------------------------------------------------------------
def _material_emissivo(nome, cor=(1.0, 1.0, 1.0), forca=2.0):
    material = bpy.data.materials.get(nome) or bpy.data.materials.new(nome)
    material.use_nodes = True
    bsdf = next(
        (n for n in material.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None
    )
    if bsdf is not None:
        bsdf.inputs["Base Color"].default_value = (*cor, 1.0)
        entrada_cor = bsdf.inputs.get("Emission Color") or bsdf.inputs.get("Emission")
        if entrada_cor is not None:
            entrada_cor.default_value = (*cor, 1.0)
        entrada_forca = bsdf.inputs.get("Emission Strength")
        if entrada_forca is not None:
            entrada_forca.default_value = forca
        bsdf.inputs["Roughness"].default_value = 1.0
    return material


def _formatar_metros(valor_m):
    return f"{valor_m:.2f}".replace(".", ",") + " m"


def _linha_cota(nome, pontos, material, espessura=0.004):
    dados = bpy.data.curves.new(nome, type="CURVE")
    dados.dimensions = "3D"
    dados.bevel_depth = espessura
    dados.bevel_resolution = 2
    spline = dados.splines.new("POLY")
    spline.points.add(len(pontos) - 1)
    for ponto, coordenada in zip(spline.points, pontos):
        ponto.co = (*coordenada, 1.0)
    objeto = bpy.data.objects.new(nome, dados)
    bpy.context.scene.collection.objects.link(objeto)
    objeto.data.materials.append(material)
    return objeto


def _texto_cota(nome, conteudo, posicao, tamanho, material, camera):
    dados = bpy.data.curves.new(nome, type="FONT")
    dados.body = conteudo
    dados.align_x = "CENTER"
    dados.align_y = "CENTER"
    dados.size = tamanho
    objeto = bpy.data.objects.new(nome, dados)
    bpy.context.scene.collection.objects.link(objeto)
    objeto.location = posicao
    objeto.data.materials.append(material)
    # Texto sempre legível: copia a rotação da câmera (billboard)
    constraint = objeto.constraints.new("COPY_ROTATION")
    constraint.target = camera
    return objeto


def _cota_linear(
    nome, p1, p2, direcao_tick, pos_texto, valor_m, material, camera, tamanho
):
    """Linha principal + delimitadores (ticks) nas pontas + rótulo central."""
    _linha_cota(f"Cota_{nome}", [p1, p2], material)
    meio_tick = 0.03
    for indice, p in enumerate((p1, p2)):
        tick = [
            (
                p[0] - direcao_tick[0] * meio_tick,
                p[1] - direcao_tick[1] * meio_tick,
                p[2] - direcao_tick[2] * meio_tick,
            ),
            (
                p[0] + direcao_tick[0] * meio_tick,
                p[1] + direcao_tick[1] * meio_tick,
                p[2] + direcao_tick[2] * meio_tick,
            ),
        ]
        _linha_cota(f"Cota_{nome}_Tick_{indice}", tick, material)
    _texto_cota(
        f"Cota_{nome}_Texto",
        _formatar_metros(valor_m),
        pos_texto,
        tamanho,
        material,
        camera,
    )


def construir_cotas(conf_balcao, conf_cotas, camera, z_tampo):
    """Sistema de cotas: largura total, profundidade, altura e módulos
    internos do balcão (quando informados no payload)."""
    largura = conf_balcao["largura_m"]
    profundidade = conf_balcao["profundidade_m"]

    material = _material_emissivo("MAT_Cota", (1.0, 1.0, 1.0), forca=2.5)
    tamanho_texto = 0.06
    desloc = 0.16  # distância da linha de cota para a face do balcão
    z_linha = 0.02

    # --- Largura total (frente do balcão) ---
    _cota_linear(
        "Largura",
        (0.0, -desloc, z_linha),
        (largura, -desloc, z_linha),
        direcao_tick=(0.0, 0.0, 1.0),
        pos_texto=(largura / 2.0, -desloc, z_linha + 0.08),
        valor_m=largura,
        material=material,
        camera=camera,
        tamanho=tamanho_texto,
    )
    # Linhas de extensão ligando as bordas do balcão à cota
    for x in (0.0, largura):
        _linha_cota(
            f"Cota_Largura_Ext_{x:.2f}",
            [(x, -0.01, z_linha), (x, -desloc - 0.03, z_linha)],
            material,
        )

    # --- Profundidade (lado direito; afastada para não ser ocluída pelo
    # corpo do balcão na elevação de 75° da câmera) ---
    desloc_prof = 0.34
    _cota_linear(
        "Profundidade",
        (largura + desloc_prof, 0.0, z_linha),
        (largura + desloc_prof, profundidade, z_linha),
        direcao_tick=(0.0, 0.0, 1.0),
        pos_texto=(largura + desloc_prof, profundidade / 2.0, z_linha + 0.08),
        valor_m=profundidade,
        material=material,
        camera=camera,
        tamanho=tamanho_texto,
    )
    for y in (0.0, profundidade):
        _linha_cota(
            f"Cota_Prof_Ext_{y:.2f}",
            [(largura + 0.01, y, z_linha), (largura + desloc_prof + 0.03, y, z_linha)],
            material,
        )

    # --- Altura (canto frontal esquerdo, vertical) ---
    _cota_linear(
        "Altura",
        (-desloc, -desloc, 0.0),
        (-desloc, -desloc, z_tampo),
        direcao_tick=(1.0, 0.0, 0.0),
        pos_texto=(-desloc - 0.10, -desloc, z_tampo / 2.0),
        valor_m=z_tampo,
        material=material,
        camera=camera,
        tamanho=tamanho_texto,
    )

    # --- Módulos/divisões internas (frente, segunda linha de cota) ---
    modulos = [m for m in conf_cotas.get("modulos_m", []) if m > 0]
    if modulos:
        soma = sum(modulos)
        if abs(soma - largura) > 0.02:
            print(
                f" > [Aviso] Módulos somam {soma:.3f} m, diferente da largura "
                f"do balcão ({largura:.3f} m). Cotas de módulo mesmo assim exibidas."
            )
        desloc_mod = desloc + 0.22
        x_inicio = 0.0
        for indice, modulo in enumerate(modulos):
            x_fim = x_inicio + modulo
            _linha_cota(
                f"Cota_Modulo_{indice}",
                [(x_inicio, -desloc_mod, z_linha), (x_fim, -desloc_mod, z_linha)],
                material,
            )
            for x in (x_inicio, x_fim):
                _linha_cota(
                    f"Cota_Modulo_{indice}_Tick_{x:.2f}",
                    [
                        (x, -desloc_mod, z_linha - 0.03),
                        (x, -desloc_mod, z_linha + 0.05),
                    ],
                    material,
                )
            _texto_cota(
                f"Cota_Modulo_{indice}_Texto",
                _formatar_metros(modulo),
                ((x_inicio + x_fim) / 2.0, -desloc_mod, z_linha + 0.08),
                tamanho_texto,
                material,
                camera,
            )
            x_inicio = x_fim


# ---------------------------------------------------------------------------
# Aceleração por GPU do Eevee — USE_GPU_ACCELERATION = true/1/yes
#
# ATENÇÃO: os dispositivos OptiX/CUDA das preferências do Cycles NÃO afetam o
# Eevee (são exclusivos do Cycles). O Eevee usa o backend de GPU global
# (preferences.system.gpu_backend), que o Blender já seleciona sozinho quando
# uma GPU está disponível. Esta rotina apenas torna a escolha EXPLÍCITA e
# desliga o ray-tracing (que não agrega a uma proposta comercial e custa tempo
# de render). Se a flag estiver ativa mas não houver GPU detectável, o Eevee
# segue em software (llvmpipe/WARP) e a métrica `render_device` acusará isso.
# ---------------------------------------------------------------------------
def _usar_aceleracao_gpu():
    valor = os.environ.get("USE_GPU_ACCELERATION", "").strip().lower()
    return valor in ("true", "1", "yes")


def configurar_aceleracao_gpu():
    """Garante que o Eevee use aceleração de hardware (backend de GPU global)
    e desliga o ray-tracing do Eevee. Ativo apenas com USE_GPU_ACCELERATION."""
    if not _usar_aceleracao_gpu():
        return

    print(" > [GPU] Configurando aceleração de hardware para Eevee...")
    sistema = bpy.context.preferences.system

    try:
        sistema.gpu_preferred_device = "AUTO"
    except Exception:
        pass

    # Backend de GPU do Eevee: prefere Vulkan, cai para OpenGL se indisponível.
    for backend in ("VULKAN", "OPENGL"):
        try:
            sistema.gpu_backend = backend
            print(f" > [GPU] Backend de GPU do Eevee definido: {backend}.")
            break
        except Exception:
            continue

    scene = bpy.context.scene
    if hasattr(scene, "eevee"):
        scene.eevee.use_raytracing = False
        print(" > [GPU] Ray-tracing do Eevee desligado (não agrega à proposta).")


# ---------------------------------------------------------------------------
# Renderização
# ---------------------------------------------------------------------------
def _configurar_color_grading(cena):
    """Color management fotográfico: AgX com look de alto contraste,
    eliminando o aspecto cinzento/desbotado da imagem.

    Em Blender 5.x o AgX não expõe mais looks de contraste (apenas 'None');
    nesse caso o look permanece 'None' (AgX já tonemapa sozinho). Em versões
    4.x o AgX aceita 'Medium High Contrast'. Filmic é fallback apenas quando
    o AgX não existe no Blender.

    Exposure -0.85 reduz a queima de brancos (arroz/batata) sem apagar as
    sombras. Curve Mapping aquece os tons médios elevando o meio da curva do
    canal R (temperatura de fotografia gastronômica ~3400 K)."""
    try:
        cena.view_settings.exposure = -0.85
    except TypeError:
        pass
    for transformacao in ("AgX", "Filmic"):
        try:
            cena.view_settings.view_transform = transformacao
        except TypeError:
            continue
        for look in ("Medium High Contrast", "High Contrast", "None"):
            try:
                cena.view_settings.look = look
                break
            except TypeError:
                continue
        break
    _configurar_curva_quente(cena)
    print(
        f" > Color management: view_transform="
        f"'{cena.view_settings.view_transform}', look='{cena.view_settings.look}', "
        f"exposure={cena.view_settings.exposure}"
    )


def _configurar_curva_quente(cena):
    """Curve Mapping aquecido: ativa use_curve_mapping e sobe o ponto médio
    do canal Vermelho (curva R com controle em x=0,5, y=0,55), aquecendo os
    tons médios e o fundo da parede sem mexer em pretos/brancos."""
    try:
        cena.view_settings.use_curve_mapping = True
        cm = cena.view_settings.curve_mapping
        curva_r = cm.curves[0]  # 0 = R, 1 = G, 2 = B, 3 = luminância
        pontos = list(curva_r.points)
        for ponto in pontos:
            if abs(ponto.location[0] - 0.5) < 0.001:
                ponto.location[1] = 0.55
                break
        else:
            curva_r.points.new(0.5, 0.55)
        cm.update()
        print(" > Curve Mapping: canal R aquecido nos tons médios (+0.05).")
    except Exception as exc:  # noqa: BLE001 - color grading é cosmético
        print(f" > [Aviso] Curve Mapping indisponível ({exc}).")


def _configurar_bloom(cena):
    """Bloom suave para destacar reflexos nos molhos e nas superfícies
    cerâmicas sem estourar a cena (threshold alto: só brilha acima do branco
    difuso). Cobre as três gerações do Eevee:

    - Eevee legado: bloom nativo do motor (threshold/knee).
    - Eevee Next <= 4.x: bloom recriado com Glare no compositor da cena
      (`scene.node_tree`).
    - Blender 5.x: compositor migrou para `scene.compositing_node_group`;
      o render entra pelo nó CompositorNodeRLayers dentro do grupo.
    Nunca quebra o render: qualquer falha vira aviso e segue sem bloom."""
    try:
        if hasattr(cena, "eevee") and hasattr(cena.eevee, "use_bloom"):
            cena.eevee.use_bloom = True
            cena.eevee.bloom_threshold = 3.5  # só especulares de metal/molho
            if hasattr(cena.eevee, "bloom_intensity"):
                cena.eevee.bloom_intensity = 0.05  # brilho suave, sem névoa
            cena.eevee.bloom_knee = 0.5
            print(" > Bloom do Eevee ativado (threshold 3.5, intensity 0.05).")
            return

        # --- Blender 5.x: compositor como node group da cena ---
        if hasattr(cena, "compositing_node_group"):
            grupo = cena.compositing_node_group
            if grupo is None:
                grupo = _criar_grupo_compositor(cena)
            try:
                cena.use_nodes = True
            except TypeError:
                pass
            _configurar_bloom_glare(grupo)
            print(" > Bloom via compositor 5.x (Glare/Bloom, threshold 3.5).")
            return

        # --- Blender <= 4.x: compositor no node_tree da cena ---
        if hasattr(cena, "node_tree"):
            cena.use_nodes = True
            arvore = cena.node_tree
            composite = next(
                (n for n in arvore.nodes if n.type == "COMPOSITE"), None
            )
            if composite is None:
                composite = arvore.nodes.new("CompositorNodeComposite")
            entrada = composite.inputs["Image"]
            if entrada.is_linked:
                origem = entrada.links[0].from_socket
                arvore.links.remove(entrada.links[0])
            else:
                camada = next((n for n in arvore.nodes if n.type == "R_LAYERS"), None)
                if camada is None:
                    camada = arvore.nodes.new("CompositorNodeRLayers")
                origem = camada.outputs["Image"]
            glare = _criar_glare(arvore)
            arvore.links.new(origem, glare.inputs["Image"])
            arvore.links.new(glare.outputs["Image"], entrada)
            print(" > Bloom via compositor (Glare/Bloom, threshold 3.5).")
            return
    except Exception as exc:  # noqa: BLE001 - bloom é cosmético, nunca falha o render
        print(f" > [Aviso] Bloom não pôde ser ativado ({exc}). Render segue sem bloom.")


def _criar_glare(arvore, glare_type="Bloom"):
    """Cria/recupera um nó Glare configurado como Bloom suave. Aceita tanto o
    Glare clássico (propriedade glare_type) quanto o socket-menu do 5.x."""
    glare = next((n for n in arvore.nodes if n.type == "GLARE"), None)
    if glare is None:
        glare = arvore.nodes.new("CompositorNodeGlare")
    if hasattr(glare, "glare_type"):
        glare.glare_type = "BLOOM"
        # Calibração anti-estouro: threshold 3.5 (o branco difuso do
        # arroz/batata NÃO ativa o brilho; só especulares de metal/molho)
        # e mix -0.95 (glare quase imperceptível sobre a imagem original).
        glare.threshold = 3.5
        glare.mix = -0.95
        glare.size = 7
        try:
            glare.quality = "HIGH"
        except TypeError:
            pass
    else:
        # Blender 5.x: parâmetros viraram sockets de entrada (não há Mix:
        # a força do brilho é controlada pelo Strength, reduzido para suavizar)
        glare.inputs["Type"].default_value = glare_type
        glare.inputs["Highlights Threshold"].default_value = 3.5
        glare.inputs["Highlights Smoothness"].default_value = 0.5
        glare.inputs["Size"].default_value = 7.0
        glare.inputs["Strength"].default_value = 0.5
    return glare


def _criar_grupo_compositor(cena):
    """Cria o node group de composição da cena (Blender 5.x) com a saída
    'Image' na interface e retorna o grupo. A entrada do render é obtida
    dentro do grupo pelo nó CompositorNodeRLayers (no 5.2 a interface de
    entrada do grupo não é alimentada pelo render)."""
    grupo = bpy.data.node_groups.new("Compositing", "CompositorNodeTree")
    cena.compositing_node_group = grupo
    grupo.interface.new_socket("Image", in_out="OUTPUT", socket_type="NodeSocketColor")
    return grupo


def _configurar_bloom_glare(grupo):
    """Liga o Glare(Bloom) entre o render (CompositorNodeRLayers) e a saída
    'Image' do node group de composição da cena (Blender 5.x)."""
    def _socket_interface(nome, in_out):
        for item in grupo.interface.items_tree:
            if (
                getattr(item, "item_type", None) == "SOCKET"
                and getattr(item, "name", None) == nome
                and getattr(item, "in_out", None) == in_out
            ):
                return
        grupo.interface.new_socket(nome, in_out=in_out, socket_type="NodeSocketColor")

    _socket_interface("Image", "OUTPUT")

    camada = next((n for n in grupo.nodes if n.type == "R_LAYERS"), None)
    if camada is None:
        camada = grupo.nodes.new("CompositorNodeRLayers")
    saida = next((n for n in grupo.nodes if n.type == "GROUP_OUTPUT"), None)
    if saida is None:
        saida = grupo.nodes.new("NodeGroupOutput")
    glare = _criar_glare(grupo)

    # Rewire idempotente: camada -> glare -> saída do grupo
    socket_saida = saida.inputs.get("Image")
    if socket_saida is not None:
        for ligacao in list(socket_saida.links):
            grupo.links.remove(ligacao)
    socket_glare_saida = glare.outputs["Image"]
    for ligacao in list(socket_glare_saida.links):
        grupo.links.remove(ligacao)
    if socket_saida is not None:
        grupo.links.new(socket_glare_saida, socket_saida)
    for ligacao in list(glare.inputs["Image"].links):
        grupo.links.remove(ligacao)
    grupo.links.new(camada.outputs["Image"], glare.inputs["Image"])


def configurar_render(conf_render, output_path):
    cena = bpy.context.scene

    motor = conf_render.get("motor", "BLENDER_EEVEE_NEXT")
    try:
        cena.render.engine = motor
    except TypeError:
        # Blender < 4.2 não conhece o identificador do Eevee Next
        print(f" > [Aviso] Motor '{motor}' indisponível. Usando 'BLENDER_EEVEE'.")
        cena.render.engine = "BLENDER_EEVEE"

    # Quantidade de amostras (o nome da propriedade mudou entre versões);
    # o env RENDER_AMOSTRAS sobrescreve o JSON para A/B sem editar código
    # (ex.: RENDER_AMOSTRAS=32 corta ~metade do tempo do Eevee).
    amostras = int(conf_render.get("amostras", 64))
    amostras_env = os.environ.get("RENDER_AMOSTRAS", "").strip()
    if amostras_env:
        try:
            amostras = int(amostras_env)
        except ValueError:
            print(
                f" > [Aviso] RENDER_AMOSTRAS inválido ('{amostras_env}'). "
                f"Usando {amostras}."
            )
    if hasattr(cena, "eevee"):
        if hasattr(cena.eevee, "taa_samples"):
            cena.eevee.taa_samples = amostras
        elif hasattr(cena.eevee, "taa_render_samples"):
            cena.eevee.taa_render_samples = amostras

    cena.render.resolution_x = int(conf_render.get("resolucao_x", 1280))
    cena.render.resolution_y = int(conf_render.get("resolucao_y", 960))
    cena.render.resolution_percentage = 100
    cena.render.image_settings.file_format = "PNG"
    cena.render.film_transparent = False

    # Pós-processamento: color grading AgX/High Contrast (elimina a imagem
    # cinzenta/desbotada) + bloom suave nos reflexos de molhos/cerâmicas.
    _configurar_color_grading(cena)
    _configurar_bloom(cena)

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    cena.render.filepath = os.path.abspath(output_path)


def main():
    job = ler_argumentos_json()
    glb_dir = job.get("glb_dir")

    inicio = time.perf_counter()
    carregar_cenario(job.get("template_path"))
    _registrar_metrica("init_sec", inicio)
    _amostrar_memoria_pico()

    configurar_aceleracao_gpu()

    # Piso + parede PBR procedurais fazem parte da fase de ambiente
    inicio = time.perf_counter()
    configurar_piso(job["balcao"])
    configurar_parede(job["balcao"])
    _registrar_metrica("environment_and_dimensions_sec", inicio)

    inicio = time.perf_counter()
    z_tampo = configurar_balcao(job["balcao"], glb_dir)
    _registrar_metrica("balcao_setup_sec", inicio)
    _amostrar_memoria_pico()

    configurar_iluminacao(job["balcao"])
    camera = configurar_camera(job.get("camera", {}), job["balcao"])

    comidas_dir = os.path.join(glb_dir, SUBPASTA_COMIDAS) if glb_dir else None
    seed_comidas = os.environ.get("COMIDA_SEED")
    if seed_comidas is not None:
        random.seed(int(seed_comidas))  # seed fixa para experimentos A/B

    # Cálculo de posições, sorteio do baralho, grade N x M e medição de Z interno
    inicio = time.perf_counter()
    deck_comidas = FoodDeckManager(comidas_dir)
    posicionar_itens(job.get("itens", []), glb_dir, z_tampo, deck_comidas)
    _registrar_metrica("food_allocation_sec", inicio)
    _amostrar_memoria_pico()

    conf_cotas = job.get("cotas", {})
    if conf_cotas.get("exibir"):
        inicio = time.perf_counter()
        construir_cotas(job["balcao"], conf_cotas, camera, z_tampo)
        _registrar_metrica("environment_and_dimensions_sec", inicio)

    configurar_render(job.get("render", {}), job["output_path"])
    saida = bpy.context.scene.render.filepath

    if SALVAR_BLEND_DEBUG:
        bpy.ops.wm.save_mainfile(filepath=CAMINHO_BLEND_DEBUG, check_existing=False)
        print(f" > [Debug] Cena salva para inspeção manual: {CAMINHO_BLEND_DEBUG}")

    if METRICAS_ATIVAS:
        # Renderiza em memória e grava o PNG separadamente, para medir de forma
        # estrita o tempo do Eevee e o tempo de escrita no disco.
        METRICAS["render_device"] = _dispositivo_render()
        _iniciar_cpu()
        inicio = time.perf_counter()
        bpy.ops.render.render(write_still=False)
        _registrar_metrica("eevee_render_sec", inicio)
        METRICAS["cpu_percent"] = _finalizar_cpu()
        _amostrar_memoria_pico()

        inicio = time.perf_counter()
        bpy.data.images["Render Result"].save_render(filepath=saida)
        _registrar_metrica("file_save_sec", inicio)
    else:
        bpy.ops.render.render(write_still=True)

    if not os.path.exists(saida):
        raise RuntimeError(
            f"Renderização concluída, mas o arquivo não foi gerado: {saida}"
        )

    if METRICAS_ATIVAS:
        _registrar_metrica("total_script_sec", _INICIO_SCRIPT)
        pacote_metricas = {
            "blender_version": bpy.app.version_string,
            "render_engine": bpy.context.scene.render.engine,
        }
        for chave, valor in METRICAS.items():
            if chave in CHAVES_METRICAS_TEMPO:
                pacote_metricas[chave] = round(valor, 6)
            elif chave == "render_device":
                pacote_metricas[chave] = valor
            else:
                pacote_metricas[chave] = round(valor, 1)
        print(f"{MARCADOR_METRICAS} {json.dumps(pacote_metricas, ensure_ascii=False)}")

    print(f"{MARCADOR_SUCESSO} {saida}")


if __name__ == "__main__":
    try:
        main()
    except Exception as erro:  # noqa: BLE001 - log completo para o wrapper
        traceback.print_exc()
        print(f"{MARCADOR_ERRO} {erro}")
        sys.exit(1)
