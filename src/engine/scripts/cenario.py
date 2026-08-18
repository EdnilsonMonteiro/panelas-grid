"""Cenário: piso, parede e balcão (GLB paramétrico ou procedural).

Módulo do pipeline de render 3D. `configurar_balcao` devolve o Z do tampo
(face superior da mesa escalada), referência para o Z das travessas.
"""

import math
import os

import bpy

from _config import GLB_BALCAO, PASTA_TEXTURAS
from utilidades import (
    _caixa_englobante,
    _importar_glb,
    _material_pbr,
    _remover_objeto,
    criar_material,
    obter_ou_criar_cubo,
)


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


def _configurar_balcao_glb(conf_balcao, caminho_glb, offset_x_m=0.0):
    """Balcão paramétrico: importa `balcao.glb` e redimensiona X (largura) e
    Y (profundidade) para casar exatamente com o payload. Retorna o Z do tampo
    (face superior da mesa escalada), referência para o Z das travessas.

    `offset_x_m` posiciona a placa no eixo X (multiplacas lado a lado)."""
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

    raiz.location = (-min_x * escala_x + offset_x_m, -min_y * escala_y, -min_z)

    z_tampo = max_z  # escala Z = 1
    print(
        f" > Balcão GLB: bbox {dim_x:.3f}x{dim_y:.3f}x{max_z - min_z:.3f} m -> "
        f"alvo {conf_balcao['largura_m']:.3f}x{conf_balcao['profundidade_m']:.3f} m | "
        f"tampo em Z={z_tampo:.3f} m"
    )
    return z_tampo


def _configurar_balcao_procedural(conf_balcao, offset_x_m=0.0):
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
        localizacao=(largura / 2.0 + offset_x_m, profundidade / 2.0, altura_corpo / 2.0),
        dimensoes=(largura, profundidade, altura_corpo),
        material=mat_corpo,
    )
    obter_ou_criar_cubo(
        "Balcao_Tampo",
        localizacao=(
            largura / 2.0 + offset_x_m,
            profundidade / 2.0,
            altura - espessura_tampo / 2.0,
        ),
        dimensoes=(largura + 0.04, profundidade + 0.04, espessura_tampo),
        material=mat_tampo,
    )
    return altura


def configurar_balcao(conf_balcao, glb_dir, placas=None):
    """Monta o(s) balcão(ões) (GLB paramétrico ou procedural) e retorna o Z do tampo.

    Com `placas` (multiplacas), cria um balcão por placa, lado a lado no eixo X."""
    if not placas:
        candidato = os.path.join(glb_dir, GLB_BALCAO) if glb_dir else None
        if candidato and os.path.exists(candidato):
            return _configurar_balcao_glb(conf_balcao, candidato)
        return _configurar_balcao_procedural(conf_balcao)

    candidato = os.path.join(glb_dir, GLB_BALCAO) if glb_dir else None
    z_max = 0.0
    for placa in placas:
        conf_placa = dict(conf_balcao)
        conf_placa["largura_m"] = placa["largura_m"]
        conf_placa["profundidade_m"] = placa["profundidade_m"]
        if candidato and os.path.exists(candidato):
            z = _configurar_balcao_glb(conf_placa, candidato, offset_x_m=placa["offset_x_m"])
        else:
            z = _configurar_balcao_procedural(conf_placa, offset_x_m=placa["offset_x_m"])
        z_max = max(z_max, z)
    return z_max