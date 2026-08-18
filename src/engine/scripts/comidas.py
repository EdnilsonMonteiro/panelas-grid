"""Comidas do render 3D: baralho sem repetição + preenchimento em grade N x M
com anti-tiling e aparo de bordas via bmesh.

Módulo do pipeline de render. A comida assenta sobre o fundo interno medido do
recipiente (cavidade), ficando logo abaixo da borda superior. O .glb da comida
é importado e normalizado uma única vez (cache) e clonado por item/célula.
"""

import glob
import math
import os
import random

import bmesh
import bpy
from mathutils import Vector

from _config import (
    CELULA_COMIDA_M,
    FATOR_BOCA_COMIDA,
    FATOR_EXPANSAO_CIRCULAR,
    FATOR_TRANSBORDO_CELULA,
    JITTER_Z_MAX_COMIDA_M,
    JITTER_Z_MIN_COMIDA_M,
    VARIACAO_ESCALA_COMIDA,
)
from utilidades import (
    _coletar_malhas,
    _comida_base_cached,
    _duplicar_hierarquia,
)


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