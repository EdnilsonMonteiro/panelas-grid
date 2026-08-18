"""Cotas dimensionais do render 3D: linhas CURVE + textos FONT virados para a
câmera (billboard).

Módulo do pipeline de render. Desenha largura total, profundidade, altura e
módulos internos do balcão (quando informados no payload).
"""

import bpy


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