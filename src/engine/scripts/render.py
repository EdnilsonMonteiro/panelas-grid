"""Renderização do Eevee: aceleração GPU, color grading, bloom e saída PNG.

Módulo do pipeline de render 3D.
"""

import os

import bpy


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