"""Configuração da câmera do render 3D.

Enquadra o balcão para ocupar `fator_ocupacao` (padrão 90%) da imagem, em
qualquer ângulo de elevação e para qualquer tamanho de mesa: a distância é
resolvida projetando o volume do balcão em espaço de câmera e ajustando a
distância até o preenchimento alvo.
"""

import math

import bpy
from mathutils import Vector


def _cantos_topo_balcao(largura, profundidade, altura):
    """4 cantos da SUPERFÍCIE do tampo (plano Z = altura).

    O enquadramento usa o tampo (onde as travessas ficam) e não o volume
    completo: em 45° a frente do balcão projetaria muito abaixo do tampo e
    forçaria uma distância maior, deixando a mesa pequena no frame.
    """
    return [
        Vector((x, y, altura))
        for x in (0.0, largura)
        for y in (0.0, profundidade)
    ]


def configurar_camera(conf_camera, conf_balcao):
    """Posiciona a câmera no ângulo de elevação configurado (padrão 45°),
    enquadrando o balcão para ocupar ~90% da imagem (ou `fator_ocupacao`),
    independentemente do tamanho da mesa."""
    largura = conf_balcao["largura_m"]
    profundidade = conf_balcao["profundidade_m"]
    altura = conf_balcao["altura_m"]

    angulo = math.radians(conf_camera.get("angulo_elevacao_graus", 45.0))
    ocupacao = conf_camera.get("fator_ocupacao")
    if ocupacao is None:
        # Compatibilidade com payloads antigos que usavam fator_margem.
        ocupacao = 1.0 / conf_camera.get("fator_margem", 1.3)
    ocupacao = min(max(float(ocupacao), 0.3), 0.97)

    alvo = Vector((largura / 2.0, profundidade / 2.0, altura))

    camera = bpy.data.objects.get("Camera")
    if camera is None:
        dados_camera = bpy.data.cameras.new("Camera")
        camera = bpy.data.objects.new("Camera", dados_camera)
        bpy.context.scene.collection.objects.link(camera)
    bpy.context.scene.camera = camera

    lente_mm = conf_camera.get("lente_mm", 50.0)
    camera.data.lens = lente_mm
    # Fit vertical: o FOV vertical é fixo pela altura do sensor (24 mm) e o
    # horizontal acompanha a proporção do render (mesmo critério do AUTO p/
    # renders paisagem, como 1280x960).
    camera.data.sensor_fit = "VERTICAL"

    cena = bpy.context.scene
    aspect_render = cena.render.resolution_x / max(cena.render.resolution_y, 1)
    sensor_h = camera.data.sensor_height
    sensor_w_efetivo = sensor_h * aspect_render

    cantos = _cantos_topo_balcao(largura, profundidade, altura)
    direcao = Vector((0.0, -math.cos(angulo), math.sin(angulo)))

    def _preencher(distancia):
        """Fração do sensor ocupada pelo balcão com a câmera à distância dada."""
        camera.location = alvo + direcao * distancia
        camera.rotation_euler = (alvo - camera.location).to_track_quat("-Z", "Y").to_euler()
        bpy.context.view_layer.update()
        matriz_cam = camera.matrix_world.inverted()
        max_x = 0.0
        max_y = 0.0
        for canto in cantos:
            p = matriz_cam @ canto
            if p.z >= 0.0:  # atrás ou no plano da câmera: não deve ocorrer
                continue
            proj_x = (p.x / -p.z) * lente_mm
            proj_y = (p.y / -p.z) * lente_mm
            max_x = max(max_x, abs(proj_x))
            max_y = max(max_y, abs(proj_y))
        return max(max_x / (sensor_w_efetivo / 2.0), max_y / (sensor_h / 2.0))

    # Busca binária da distância para atingir a ocupação alvo (a fração
    # preenchida cai monotonicamente com a distância).
    d_min = 0.3
    d_max = max(20.0 * max(largura, profundidade, altura), 4.0)
    for _ in range(35):
        d_meio = (d_min + d_max) / 2.0
        if _preencher(d_meio) > ocupacao:
            d_min = d_meio  # precisa afastar para caber
        else:
            d_max = d_meio  # pode aproximar para preencher mais
    distancia = (d_min + d_max) / 2.0

    camera.location = alvo + direcao * distancia
    camera.rotation_euler = (alvo - camera.location).to_track_quat("-Z", "Y").to_euler()
    bpy.context.view_layer.update()
    return camera