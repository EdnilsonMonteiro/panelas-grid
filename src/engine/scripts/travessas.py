"""Travessas (itens) do render 3D.

Cria/importa os recipientes (cubas retangulares e panelas circulares) a partir
do payload do job, posiciona-os sobre o tampo e dispara o preenchimento de
comida via `comidas.posicionar_comida`.
"""

import os

import bpy
from mathutils import Vector

from _config import PALETA_PADRAO
from comidas import posicionar_comida
from utilidades import (
    _caixa_englobante,
    _duplicar_hierarquia,
    _importar_glb_cached,
    criar_material,
)


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