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
       retangulares com anti-tiling (rotação Z aleatória em 0/90/180/270°,
       espelhamento aleatório em X/Y em 50% das células, jitter de altura Z
       ±2-5 mm e variação de escala por cópia), preservando as bordas
       visíveis. Formato "circulo" sorteia apenas entre arroz/feijao/
       macarrao (peça única).
    6. Erguer piso e parede como planos procedurais com materiais PBR
       construídos a partir de `assets/textures/piso/` (tiling via nó
       Mapping) e `assets/textures/parede/` (detecta dinamicamente mapa
       Specular vs Roughness).
    7. Iluminar a cena como estúdio de fotografia de alimentos: World HDRI
       dinâmico de `assets/textures/hdri/` (`.hdr`/`.exr`, Strength 0.8) +
       2 area lights quentes (~3800 K, 30-80 W) acima e inclinadas sobre o
       balcão, calibradas para não estourar os brancos.
    8. Desenhar cotas dimensionais (linhas CURVE brancas emissivas + textos
       FONT com constraint de rotação para a câmera) em metros.
    9. Configurar o renderizador `BLENDER_EEVEE_NEXT`, o color management
       (`AgX` com fallback `Filmic`, look Medium High Contrast/None, exposure
       -0.85 e Curve Mapping com canal R aquecido ~3400 K), o bloom suave
       (threshold 3.5) e gerar a imagem `.png`.

Contrato do JSON de entrada (todas as medidas em METROS, coordenadas no
CENTRO da peça, eixo Z apontando para cima):
    {
        "template_path": "caminho/para/cenario_template.blend",
        "output_path":   "caminho/para/render.png",
        "glb_dir":       "caminho/para/assets/glb",
        "balcao": {"largura_m": 1.90, "profundidade_m": 0.95,
                   "altura_m": 0.90, "espessura_tampo_m": 0.05},
        "camera": {"angulo_elevacao_graus": 45.0, "fator_ocupacao": 0.9},
        "cotas":  {"exibir": true, "modulos_m": [1.20, 0.51, 0.61]},
        "render": {"motor": "BLENDER_EEVEE_NEXT",
                   "resolucao_x": 1280, "resolucao_y": 960, "amostras": 64},
        "itens": [{"nome": "Cuba G", "formato": "retangulo",
                   "glb": "cuba_g.glb" | null,
                   "x": 0.10, "y": 0.47, "z": 0.90,
                   "largura_m": 0.21, "profundidade_m": 0.53,
                   "altura_m": 0.15, "cor": [0.8, 0.8, 0.8]}]
    }

Estrutura modular: este arquivo é apenas a ORQUESTRAÇÃO (`main`). A lógica
vive em módulos irmãos deste mesmo diretório (`_config`, `metricas`,
`utilidades`, `cenario`, `camera`, `iluminacao`, `travessas`, `comidas`,
`cotas` e `render`), importados abaixo. O diretório do script é inserido em
`sys.path` para garantir os imports com `blender -b -P` independentemente do
diretório de trabalho.

Marcadores de stdout consumidos pelo wrapper (`blender_headless.py`):
    [RENDER_3D_OK] <caminho_png>
    [RENDER_3D_ERRO] <mensagem>
    [RENDER_METRICS_JSON] <json de métricas>   (quando ENABLE_RENDER_METRICS)
"""

import json
import os
import random
import sys
import time
import traceback

import bpy

# Garante que os módulos irmãos deste diretório sejam importáveis quando o
# script roda via `blender -b -P <caminho>/blender_render_script.py`.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _config import CAMINHO_BLEND_DEBUG, SALVAR_BLEND_DEBUG, SUBPASTA_COMIDAS
from camera import configurar_camera
from cenario import configurar_balcao, configurar_parede, configurar_piso
from comidas import FoodDeckManager
from cotas import construir_cotas
from iluminacao import carregar_cenario, configurar_iluminacao
from metricas import (
    CHAVES_METRICAS_TEMPO,
    METRICAS,
    METRICAS_ATIVAS,
    _INICIO_SCRIPT,
    _amostrar_memoria_pico,
    _dispositivo_render,
    _finalizar_cpu,
    _iniciar_cpu,
    _registrar_metrica,
)
from render import configurar_aceleracao_gpu, configurar_render
from travessas import posicionar_itens
from utilidades import ler_argumentos_json

MARCADOR_SUCESSO = "[RENDER_3D_OK]"
MARCADOR_ERRO = "[RENDER_3D_ERRO]"
MARCADOR_METRICAS = "[RENDER_METRICS_JSON]"


def main():
    job = ler_argumentos_json()
    glb_dir = job.get("glb_dir")

    inicio = time.perf_counter()
    carregar_cenario(job.get("template_path"))
    _registrar_metrica("init_sec", inicio)
    _amostrar_memoria_pico()

    configurar_aceleracao_gpu()

    # Piso + parede PBR procedurais fazem parte da fase de ambiente
    inicio = time.perf_counter()
    configurar_piso(job["balcao"])
    configurar_parede(job["balcao"])
    _registrar_metrica("environment_and_dimensions_sec", inicio)

    inicio = time.perf_counter()
    z_tampo = configurar_balcao(job["balcao"], glb_dir, job.get("placas"))
    _registrar_metrica("balcao_setup_sec", inicio)
    _amostrar_memoria_pico()

    configurar_iluminacao(job["balcao"])

    # Resolução/motor definidos ANTES da câmera: o enquadramento (fator de
    # ocupação) depende da proporção final do render.
    configurar_render(job.get("render", {}), job["output_path"])
    saida = bpy.context.scene.render.filepath
    camera = configurar_camera(job.get("camera", {}), job["balcao"])

    comidas_dir = os.path.join(glb_dir, SUBPASTA_COMIDAS) if glb_dir else None
    seed_comidas = os.environ.get("COMIDA_SEED")
    if seed_comidas is not None:
        random.seed(int(seed_comidas))  # seed fixa para experimentos A/B

    # Cálculo de posições, sorteio do baralho, grade N x M e medição de Z interno
    inicio = time.perf_counter()
    deck_comidas = FoodDeckManager(comidas_dir)
    posicionar_itens(job.get("itens", []), glb_dir, z_tampo, deck_comidas)
    _registrar_metrica("food_allocation_sec", inicio)
    _amostrar_memoria_pico()

    conf_cotas = job.get("cotas", {})
    if conf_cotas.get("exibir"):
        inicio = time.perf_counter()
        construir_cotas(job["balcao"], conf_cotas, camera, z_tampo)
        _registrar_metrica("environment_and_dimensions_sec", inicio)

    if SALVAR_BLEND_DEBUG:
        bpy.ops.wm.save_mainfile(filepath=CAMINHO_BLEND_DEBUG, check_existing=False)
        print(f" > [Debug] Cena salva para inspeção manual: {CAMINHO_BLEND_DEBUG}")

    if METRICAS_ATIVAS:
        # Renderiza em memória e grava o PNG separadamente, para medir de forma
        # estrita o tempo do Eevee e o tempo de escrita no disco.
        METRICAS["render_device"] = _dispositivo_render()
        _iniciar_cpu()
        inicio = time.perf_counter()
        bpy.ops.render.render(write_still=False)
        _registrar_metrica("eevee_render_sec", inicio)
        METRICAS["cpu_percent"] = _finalizar_cpu()
        _amostrar_memoria_pico()

        inicio = time.perf_counter()
        bpy.data.images["Render Result"].save_render(filepath=saida)
        _registrar_metrica("file_save_sec", inicio)
    else:
        bpy.ops.render.render(write_still=True)

    if not os.path.exists(saida):
        raise RuntimeError(
            f"Renderização concluída, mas o arquivo não foi gerado: {saida}"
        )

    if METRICAS_ATIVAS:
        _registrar_metrica("total_script_sec", _INICIO_SCRIPT)
        pacote_metricas = {
            "blender_version": bpy.app.version_string,
            "render_engine": bpy.context.scene.render.engine,
        }
        for chave, valor in METRICAS.items():
            if chave in CHAVES_METRICAS_TEMPO:
                pacote_metricas[chave] = round(valor, 6)
            elif chave == "render_device":
                pacote_metricas[chave] = valor
            else:
                pacote_metricas[chave] = round(valor, 1)
        print(f"{MARCADOR_METRICAS} {json.dumps(pacote_metricas, ensure_ascii=False)}")

    print(f"{MARCADOR_SUCESSO} {saida}")


if __name__ == "__main__":
    try:
        main()
    except Exception as erro:  # noqa: BLE001 - log completo para o wrapper
        traceback.print_exc()
        print(f"{MARCADOR_ERRO} {erro}")
        sys.exit(1)