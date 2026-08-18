"""Iluminação e cenário base do render 3D.

World HDRI dinâmico + 2 area lights quentes (food photography) + carga do
template .blend. Módulo do pipeline de render.
"""

import glob
import math
import os

import bpy
from mathutils import Vector

from _config import (
    COR_LUZ_QUENTE,
    INTENSIDADE_HDRI,
    PASTAS_HDRI,
    SATURACAO_HDRI,
    TOM_HDRI,
)
from utilidades import _remover_objeto


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