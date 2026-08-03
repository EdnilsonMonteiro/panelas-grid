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
       retangulares (rotação Z aleatória em 0/90/180/270° e variação de
       escala ±5% por cópia), preservando as bordas visíveis. Formato
       "circulo" sorteia apenas entre arroz/feijao/macarrao (peça única).
    6. Erguer piso e parede como planos procedurais com materiais PBR
       construídos a partir de `assets/textures/piso/` (tiling via nó
       Mapping) e `assets/textures/parede/` (detecta dinamicamente mapa
       Specular vs Roughness).
    7. Desenhar cotas dimensionais (linhas CURVE brancas emissivas + textos
       FONT com constraint de rotação para a câmera) em metros.
    8. Configurar o renderizador `BLENDER_EEVEE_NEXT` e gerar a imagem `.png`.

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
import traceback

import bmesh
import bpy
from mathutils import Vector

MARCADOR_SUCESSO = "[RENDER_3D_OK]"
MARCADOR_ERRO = "[RENDER_3D_ERRO]"

# Os modelos .glb (cubas, panelas e comidas) são importados na orientação
# original do arquivo: já vêm modelados "em pé" (abertura/base alinhadas
# aos eixos), portanto NENHUMA correção de rotação é aplicada.

# [Debug temporário] Salva a cena montada em .blend para inspeção manual.
RAIZ_PROJETO = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..")
)
SALVAR_BLEND_DEBUG = True
CAMINHO_BLEND_DEBUG = os.path.join(RAIZ_PROJETO, "assets", "debug_ultimo_render.blend")

# Assets de cenário/comida resolvidos a partir dos diretórios do projeto.
GLB_BALCAO = "balcao.glb"
SUBPASTA_COMIDAS = "comidas"
PASTA_TEXTURAS = os.path.join(RAIZ_PROJETO, "assets", "textures")

# Encaixe da comida na boca do recipiente: fração da abertura ocupada (~88%),
# mantendo as bordas do recipiente visíveis ao redor.
FATOR_BOCA_COMIDA = 0.88

# Preenchimento em grade: tamanho alvo de cada célula da grade (garante
# grades >= 2x2 nas cubas de 21 cm), variação de escala por cópia, overlap
# agressivo entre células (1.40: cobre o "vale" do perfil morro dos assets,
# medido em ~10-20% da bbox por borda) e jitter vertical por cópia (8 mm:
# quebra o vale coplanar e dá relevo natural). Env vars COMIDA_TRANSBORDO /
# COMIDA_JITTER_Z / COMIDA_SEED permitem experimentos A/B sem editar código.
CELULA_COMIDA_M = 0.10
VARIACAO_ESCALA_COMIDA = 0.02
FATOR_TRANSBORDO_CELULA = float(os.environ.get("COMIDA_TRANSBORDO", "1.40"))
JITTER_Z_COMIDA_M = float(os.environ.get("COMIDA_JITTER_Z", "0.008"))

PALETA_PADRAO = [
    (0.62, 0.35, 0.17),  # terracota
    (0.20, 0.45, 0.62),  # azul aço
    (0.35, 0.55, 0.30),  # verde oliva
    (0.65, 0.55, 0.25),  # mostarda
    (0.50, 0.30, 0.45),  # vinho
]


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


def configurar_iluminacao():
    sol = bpy.data.objects.get("Sol")
    if sol is None:
        dados_sol = bpy.data.lights.new("Sol", type="SUN")
        sol = bpy.data.objects.new("Sol", dados_sol)
        bpy.context.scene.collection.objects.link(sol)
    sol.data.energy = 2.0
    sol.data.angle = math.radians(30.0)
    sol.rotation_euler = (math.radians(50), math.radians(-15), math.radians(35))

    mundo = bpy.context.scene.world
    if mundo is None:
        mundo = bpy.data.worlds.new("Mundo")
        bpy.context.scene.world = mundo
    mundo.use_nodes = True
    fundo = mundo.node_tree.nodes.get("Background")
    if fundo is not None:
        fundo.inputs["Color"].default_value = (0.85, 0.87, 0.92, 1.0)
        fundo.inputs["Strength"].default_value = 0.35


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
    vértices suficientes."""
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

    Os materiais/texturas originais do .glb são preservados; o material de
    fallback (cor chapada) só é aplicado em malhas importadas sem material.
    """
    objetos_antes = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=caminho_glb)
    importados = [o for o in bpy.data.objects if o not in objetos_antes]
    if not importados:
        raise RuntimeError(f"Nenhum objeto importado de '{caminho_glb}'.")

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
    # fallback para malhas que vieram sem nenhum material.
    for objeto in importados:
        if objeto.type == "MESH" and not objeto.data.materials:
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
    A escala é uniforme, portanto não há cisalhamento ao combinar rotação."""
    raiz = bpy.data.objects.new(f"COMIDA_{nome}_{sufixo}", None)
    bpy.context.scene.collection.objects.link(raiz)
    for topo in tops:
        topo.parent = raiz
    raiz.rotation_euler = (0.0, 0.0, math.radians(rotacao_z_graus))
    raiz.scale = (escala, escala, escala) if not isinstance(escala, tuple) else escala
    raiz.location = posicao
    return raiz


def _aparar_comida_circular(tops, item, z_base):
    """Apara as quinas da comida que vazam para fora da borda circular da
    panela: Boolean INTERSECT em cada malha da comida contra um cilindro
    auxiliar do tamanho da abertura interna (removido ao final)."""
    raio = (item["largura_m"] * FATOR_BOCA_COMIDA) / 2.0
    bpy.ops.mesh.primitive_cylinder_add(
        radius=raio,
        depth=2.0,
        vertices=64,
        location=(item["x"], item["y"], z_base + 1.0 - 0.01),
    )
    cilindro = bpy.context.active_object
    cilindro.name = f"CORTE_{item['nome']}"

    pilha = list(tops)
    while pilha:
        objeto = pilha.pop()
        pilha.extend(objeto.children)
        if objeto.type != "MESH":
            continue
        modificador = objeto.modifiers.new("CorteCircular", "BOOLEAN")
        modificador.operation = "INTERSECT"
        modificador.object = cilindro
        bpy.context.view_layer.objects.active = objeto
        bpy.ops.object.modifier_apply(modifier=modificador.name)

    bpy.data.objects.remove(cilindro, do_unlink=True)


def _aparar_grade_retangular(raizes, item):
    """Apara o que vaza das bordas retangulares da cuba removendo os VÉRTICES
    (bmesh) fora da boca útil do recipiente (88% da abertura): toda face com
    um vértice fora é eliminada, garantindo spill zero e borda limpa (entalhes
    de ~2-4 mm, escondidos pela parede da cuba).

    Não usa Boolean (malhas do Tripo são não-manifold e o solver as esvazia)
    nem bake (preserva as normais originais da malha). Determinístico e rápido."""
    abertura_x = item["largura_m"] * FATOR_BOCA_COMIDA
    abertura_y = item["profundidade_m"] * FATOR_BOCA_COMIDA
    meia_x = abertura_x / 2.0
    meia_y = abertura_y / 2.0
    cx = item["x"]
    cy = item["y"]

    malhas = []
    pilha = list(raizes)
    while pilha:
        objeto = pilha.pop()
        if objeto.type == "MESH":
            malhas.append(objeto)
        pilha.extend(objeto.children)

    bpy.context.view_layer.update()
    for malha in malhas:
        if malha.data.users > 1:
            malha.data = malha.data.copy()  # copias da grade compartilham o mesh
        mundo = malha.matrix_world
        bm = bmesh.new()
        bm.from_mesh(malha.data)
        bm.verts.ensure_lookup_table()
        fora = [
            v
            for v in bm.verts
            if abs((mundo @ v.co).x - cx) > meia_x
            or abs((mundo @ v.co).y - cy) > meia_y
        ]
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
      sem cisalhamento), rotação Z aleatória, variação de escala ±2%,
      overlap 1.40 e jitter Z de 8 mm. O que vaza das bordas retangulares é
      aparado removendo as faces fora da boca útil (bmesh, sem Boolean).
    - Círculo: peça única centralizada, dimensionada a ~88% da abertura, com
      as quinas aparadas na borda circular (Boolean INTERSECT).
    A comida assenta sobre o fundo interno medido do recipiente (cavidade),
    ficando logo abaixo da borda superior."""
    print(f" > Comida para '{item['nome']}': {os.path.basename(caminho_comida)}")
    importados = _importar_glb(caminho_comida)
    caixa = _caixa_englobante(importados)
    if caixa is None:
        raise RuntimeError(f"Comida '{caminho_comida}' não contém malhas.")

    (min_x, max_x), (min_y, max_y), (min_z, _) = caixa
    dim_x = max(max_x - min_x, 1e-6)
    dim_y = max(max_y - min_y, 1e-6)

    # Normaliza o modelo: centro da footprint na origem e base em Z=0
    centro_x = (min_x + max_x) / 2.0
    centro_y = (min_y + max_y) / 2.0
    tops = [o for o in importados if o.parent is None]
    for topo in tops:
        topo.location = (
            topo.location.x - centro_x,
            topo.location.y - centro_y,
            topo.location.z - min_z,
        )

    # Assenta na cavidade interna (fundo medido; fallback: face superior)
    z_base = item.get("z_fundo_interno", z_tampo + item.get("altura_m", 0.15)) + 0.005

    abertura_x = item["largura_m"] * FATOR_BOCA_COMIDA
    abertura_y = item["profundidade_m"] * FATOR_BOCA_COMIDA

    if item.get("formato") == "circulo":
        _montar_instancia_comida(
            tops,
            item["nome"],
            "0",
            posicao=(item["x"], item["y"], z_base),
            rotacao_z_graus=0.0,
            escala=(
                abertura_x / dim_x,
                abertura_y / dim_y,
                abertura_x / dim_x,
            ),
        )
        # Corte perfeito: apara as quinas da comida na borda circular
        _aparar_comida_circular(tops, item, z_base)
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

    primeira = True
    raizes = []
    for i in range(qtd_x):
        for j in range(qtd_y):
            offset_x = (i + 0.5) * celula_x - abertura_x / 2.0
            offset_y = (j + 0.5) * celula_y - abertura_y / 2.0
            alvos = tops if primeira else _duplicar_hierarquia(tops)
            primeira = False
            rotacao = random.choice((0.0, 90.0, 180.0, 270.0))
            fator = random.uniform(
                1.0 - VARIACAO_ESCALA_COMIDA, 1.0 + VARIACAO_ESCALA_COMIDA
            )
            fator *= FATOR_TRANSBORDO_CELULA  # folhas transbordam a célula
            # Jitter Z: quebra o vale coplanar entre instâncias vizinhas
            jitter_z = random.uniform(0.0, JITTER_Z_COMIDA_M)
            # Escala por eixo preenchendo a célula; nas rotações de 90/270°
            # os eixos do modelo trocam (R @ S: escala local, depois gira)
            if rotacao in (90.0, 270.0):
                escala_local_x = celula_y / dim_x
                escala_local_y = celula_x / dim_y
            else:
                escala_local_x = celula_x / dim_x
                escala_local_y = celula_y / dim_y
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
                    escala_local_x * fator,
                ),
            )
            raizes.append(raiz)

    # Apara o que vaza para fora das bordas retangulares da cuba
    _aparar_grade_retangular(raizes, item)


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
# Renderização
# ---------------------------------------------------------------------------
def configurar_render(conf_render, output_path):
    cena = bpy.context.scene

    motor = conf_render.get("motor", "BLENDER_EEVEE_NEXT")
    try:
        cena.render.engine = motor
    except TypeError:
        # Blender < 4.2 não conhece o identificador do Eevee Next
        print(f" > [Aviso] Motor '{motor}' indisponível. Usando 'BLENDER_EEVEE'.")
        cena.render.engine = "BLENDER_EEVEE"

    # Quantidade de amostras (o nome da propriedade mudou entre versões)
    amostras = int(conf_render.get("amostras", 64))
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

    # "Standard" mantém as cores das travessas vivas para a proposta comercial
    # (o AgX, padrão do Blender 4.x/5.x, dessatura demais a imagem).
    try:
        cena.view_settings.view_transform = "Standard"
    except TypeError:
        pass

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    cena.render.filepath = os.path.abspath(output_path)


def main():
    job = ler_argumentos_json()
    glb_dir = job.get("glb_dir")

    carregar_cenario(job.get("template_path"))
    configurar_piso(job["balcao"])
    configurar_parede(job["balcao"])
    z_tampo = configurar_balcao(job["balcao"], glb_dir)
    configurar_iluminacao()
    camera = configurar_camera(job.get("camera", {}), job["balcao"])

    comidas_dir = os.path.join(glb_dir, SUBPASTA_COMIDAS) if glb_dir else None
    seed_comidas = os.environ.get("COMIDA_SEED")
    if seed_comidas is not None:
        random.seed(int(seed_comidas))  # seed fixa para experimentos A/B
    deck_comidas = FoodDeckManager(comidas_dir)
    posicionar_itens(job.get("itens", []), glb_dir, z_tampo, deck_comidas)

    conf_cotas = job.get("cotas", {})
    if conf_cotas.get("exibir"):
        construir_cotas(job["balcao"], conf_cotas, camera, z_tampo)

    configurar_render(job.get("render", {}), job["output_path"])

    if SALVAR_BLEND_DEBUG:
        bpy.ops.wm.save_mainfile(filepath=CAMINHO_BLEND_DEBUG, check_existing=False)
        print(f" > [Debug] Cena salva para inspeção manual: {CAMINHO_BLEND_DEBUG}")

    bpy.ops.render.render(write_still=True)

    saida = bpy.context.scene.render.filepath
    if not os.path.exists(saida):
        raise RuntimeError(
            f"Renderização concluída, mas o arquivo não foi gerado: {saida}"
        )

    print(f"{MARCADOR_SUCESSO} {saida}")


if __name__ == "__main__":
    try:
        main()
    except Exception as erro:  # noqa: BLE001 - log completo para o wrapper
        traceback.print_exc()
        print(f"{MARCADOR_ERRO} {erro}")
        sys.exit(1)
