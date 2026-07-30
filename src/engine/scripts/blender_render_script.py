"""Script executado INTERNAMENTE pelo Blender (modo headless).

Uso:
    blender -b -P blender_render_script.py -- <json_inline_ou_caminho_json>

Responsabilidades (conforme SPEC_3D_RENDER.md):
    1. Carregar `templates/cenario_template.blend` (se existir; caso contrário
       monta um cenário procedural equivalente).
    2. Ler os argumentos JSON enviados pela linha de comando.
    3. Importar os arquivos `.glb` das travessas e aplicar as transformações
       de posição (x, y, z). Travessas sem `.glb` recebem uma malha procedural
       (cilindro para formato "circulo", caixa para "retangulo").
    4. Configurar o renderizador `BLENDER_EEVEE_NEXT` e gerar a imagem `.png`.

Contrato do JSON de entrada (todas as medidas em METROS, coordenadas no
CENTRO da peça, eixo Z apontando para cima):
    {
        "template_path": "caminho/para/cenario_template.blend",
        "output_path":   "caminho/para/render.png",
        "glb_dir":       "caminho/para/assets/glb",
        "balcao": {"largura_m": 1.90, "profundidade_m": 0.95,
                   "altura_m": 0.90, "espessura_tampo_m": 0.05},
        "camera": {"angulo_elevacao_graus": 75.0, "fator_margem": 1.30},
        "render": {"motor": "BLENDER_EEVEE_NEXT",
                   "resolucao_x": 1280, "resolucao_y": 960, "amostras": 64},
        "itens": [{"nome": "Cuba G", "formato": "retangulo",
                   "glb": "cuba_g.glb" | null,
                   "x": 0.10, "y": 0.47, "z": 0.90,
                   "largura_m": 0.21, "profundidade_m": 0.53,
                   "altura_m": 0.15, "cor": [0.8, 0.8, 0.8]}]
    }
"""

import json
import math
import os
import sys
import traceback

import bpy
from mathutils import Vector

MARCADOR_SUCESSO = "[RENDER_3D_OK]"
MARCADOR_ERRO = "[RENDER_3D_ERRO]"

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


def configurar_chao():
    material = criar_material("MAT_Chao", (0.42, 0.42, 0.46), rugosidade=0.9)
    chao = obter_ou_criar_cubo(
        "Chao", localizacao=(0.0, 0.0, -0.05), dimensoes=(30.0, 30.0, 0.1)
    )
    chao.data.materials.clear()
    chao.data.materials.append(material)
    return chao


def configurar_balcao(conf_balcao):
    """Monta o corpo do balcão e o tampo sobre o qual as travessas ficam."""
    largura = conf_balcao["largura_m"]
    profundidade = conf_balcao["profundidade_m"]
    altura = conf_balcao["altura_m"]
    espessura_tampo = conf_balcao.get("espessura_tampo_m", 0.05)

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


def importar_travessa_glb(item, caminho_glb, material):
    """Importa o .glb e aplica posição/escala para casar com a footprint do layout."""
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

    (min_x, max_x), (min_y, max_y), (min_z, _) = caixa
    dim_x = max(max_x - min_x, 1e-6)
    dim_y = max(max_y - min_y, 1e-6)

    escala_x = item["largura_m"] / dim_x
    escala_y = item["profundidade_m"] / dim_y
    escala_z = escala_x

    raiz.scale = (escala_x, escala_y, escala_z)

    centro_x = (min_x + max_x) / 2.0
    centro_y = (min_y + max_y) / 2.0
    raiz.location = (
        item["x"] - centro_x * escala_x,
        item["y"] - centro_y * escala_y,
        item["z"] - min_z * escala_z,  # base da peça apoiada sobre o tampo
    )

    for objeto in importados:
        _aplicar_material(objeto, material)
    return raiz


def posicionar_itens(itens, glb_dir):
    for indice, item in enumerate(itens):
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

    carregar_cenario(job.get("template_path"))
    configurar_chao()
    configurar_balcao(job["balcao"])
    configurar_iluminacao()
    configurar_camera(job.get("camera", {}), job["balcao"])
    posicionar_itens(job.get("itens", []), job.get("glb_dir"))
    configurar_render(job.get("render", {}), job["output_path"])

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
