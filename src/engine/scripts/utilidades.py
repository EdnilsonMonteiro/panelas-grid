"""Utilidades compartilhadas do pipeline de render 3D (Blender/bpy).

Agrupa operações genéricas de cena usadas por vários módulos: entrada de
dados JSON, materiais, importação com cache de GLB, texturas PBR, bounding
boxes e duplicação de hierarquias.
"""

import glob
import json
import os
import sys

import bmesh
import bpy
from mathutils import Vector

# Cache de imports GLB: os .glb (travessas e comidas) são importados UMA única
# vez por arquivo e clonados por item via `_duplicar_hierarquia` (malhas,
# materiais e texturas compartilhados, transform independente). No job típico
# isso reduz de ~48 imports GLTF para ~10 (2 travessas únicas + 8 comidas).
CACHE_GLB = {}


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