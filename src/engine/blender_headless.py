"""Wrapper Python para execução do Blender em modo headless (SPEC_3D_RENDER.md).

Responsabilidades:
    - Montar o "job" de renderização (JSON) a partir dos itens calculados
      pelo motor geométrico (`LayoutEngine`), convertendo cm -> metros.
    - Executar o comando `blender -b -P <script> -- <json>` via subprocess.
    - Validar o resultado e devolver o caminho do PNG gerado.

O executável do Blender é localizado pela variável de ambiente `BLENDER_PATH`;
caso ausente, assume-se que `blender` está no PATH do sistema.
"""

import colorsys
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import unicodedata

DIRETORIO_ENGINE = os.path.dirname(os.path.abspath(__file__))
RAIZ_PROJETO = os.path.abspath(os.path.join(DIRETORIO_ENGINE, "..", ".."))

CAMINHO_SCRIPT_BLENDER = os.path.join(
    DIRETORIO_ENGINE, "scripts", "blender_render_script.py"
)
CAMINHO_TEMPLATE_PADRAO = os.path.join(
    RAIZ_PROJETO, "templates", "cenario_template.blend"
)
DIRETORIO_GLB_PADRAO = os.path.join(RAIZ_PROJETO, "assets", "glb")

MARCADOR_SUCESSO = "[RENDER_3D_OK]"
MARCADOR_METRICAS = "[RENDER_METRICS_JSON]"

GAP_PLACAS_CM = 1.0  # espaçamento entre placas (multiplacas)


class BlenderNaoEncontradoError(RuntimeError):
    """Levantada quando o executável do Blender não está disponível."""


class FalhaRenderizacaoBlenderError(RuntimeError):
    """Levantada quando o Blender executa, mas falha ao renderizar."""


# ---------------------------------------------------------------------------
# Localização do executável
# ---------------------------------------------------------------------------
def obter_executavel_blender():
    """Retorna o executável configurado (env BLENDER_PATH) ou 'blender' do PATH.

    Tolerante a BLENDER_PATH apontando para a PASTA de instalação do Blender
    (ex.: 'C:\\Program Files\\Blender Foundation\\Blender 5.2'): nesse caso,
    completa automaticamente com o binário ('blender.exe' no Windows).
    """
    executavel = os.environ.get("BLENDER_PATH", "blender")
    if os.path.isdir(executavel):
        nome_binario = "blender.exe" if os.name == "nt" else "blender"
        candidato = os.path.join(executavel, nome_binario)
        if os.path.exists(candidato):
            return candidato
    return executavel


def blender_disponivel():
    """True se o executável do Blender pode ser invocado nesta máquina."""
    executavel = obter_executavel_blender()
    if os.path.isabs(executavel) or os.sep in executavel:
        return os.path.exists(executavel)
    return shutil.which(executavel) is not None


# ---------------------------------------------------------------------------
# Montagem do job (função pura, testável sem Blender)
# ---------------------------------------------------------------------------
def slugify(nome):
    """Converte 'Cuba G (R)' em 'cuba_g_r' para localizar o arquivo .glb."""
    normalizado = unicodedata.normalize("NFD", str(nome))
    sem_acento = "".join(c for c in normalizado if unicodedata.category(c) != "Mn")
    return re.sub(r"_+", "_", re.sub(r"[^a-z0-9]+", "_", sem_acento.lower())).strip("_")


def cor_deterministica(nome):
    """Gera uma cor RGB (0-1) estável a partir do nome, para distinguir peças."""
    digest = hashlib.md5(str(nome).encode("utf-8")).hexdigest()
    matiz = int(digest[:4], 16) / 0xFFFF
    r, g, b = colorsys.hsv_to_rgb(matiz, 0.55, 0.85)
    return [round(r, 4), round(g, 4), round(b, 4)]


def montar_job_render(
    itens_layout,
    largura_balcao_cm,
    profundidade_balcao_cm,
    caminho_saida_png,
    *,
    altura_balcao_cm=90.0,
    espessura_tampo_cm=5.0,
    alturas_itens_cm=None,
    template_path=None,
    glb_dir=None,
    resolucao=(1280, 960),
    amostras=64,
    angulo_camera_graus=45.0,
    exibir_cotas=False,
    modulos_balcao_cm=None,
):
    """Converte os itens do motor geométrico (cm, canto superior-esquerdo) no
    JSON de renderização (metros, centro da peça, Z sobre o tampo do balcão).

    `alturas_itens_cm` permite customizar a altura 3D das peças por formato:
    {"circulo": 20.0, "retangulo": 15.0}.

    `exibir_cotas` liga o overlay de cotas dimensionais; `modulos_balcao_cm`
    lista as divisões internas do balcão (ex: [120, 51, 61]) para as cotas
    de módulos.
    """
    glb_dir = os.path.abspath(glb_dir or DIRETORIO_GLB_PADRAO)
    template_path = os.path.abspath(template_path or CAMINHO_TEMPLATE_PADRAO)
    alturas = {"circulo": 20.0, "retangulo": 15.0}
    if alturas_itens_cm:
        alturas.update(alturas_itens_cm)

    # O env RENDER_AMOSTRAS sobrescreve o valor do parâmetro (default 64),
    # permitindo A/B de qualidade x velocidade sem editar código.
    try:
        amostras = int(os.environ.get("RENDER_AMOSTRAS", amostras))
    except ValueError:
        pass

    z_tampo_m = round(altura_balcao_cm / 100.0, 4)

    ARQUIVO_BASE_RETANGULAR = "cuba_meio.glb"
    ARQUIVO_BASE_CIRCULAR = "panela_30.glb"
    itens_3d = []
    for item in itens_layout:
        formato = item.get("formato", "retangulo")
        slug = slugify(item["nome"])

        glb = None

        if os.path.exists(os.path.join(glb_dir, f"{slug}.glb")):
            glb = f"{slug}.glb"
        elif formato == "retangulo" and os.path.exists(
            os.path.join(glb_dir, ARQUIVO_BASE_RETANGULAR)
        ):
            print(f"DEGUG - Item {slug} está com base retangular")
            glb = ARQUIVO_BASE_RETANGULAR
        elif formato == "circulo" and os.path.exists(
            os.path.join(glb_dir, ARQUIVO_BASE_CIRCULAR)
        ):
            glb = ARQUIVO_BASE_CIRCULAR

        itens_3d.append(
            {
                "nome": item["nome"],
                "formato": formato,
                "glb": glb,
                # Layout trabalha com o canto (x, y); Blender usa o centro da peça
                "x": round((item["x"] + item["w"] / 2.0) / 100.0, 4),
                "y": round((item["y"] + item["h"] / 2.0) / 100.0, 4),
                "z": z_tampo_m,
                "largura_m": round(item["w"] / 100.0, 4),
                "profundidade_m": round(item["h"] / 100.0, 4),
                "altura_m": round(alturas.get(formato, 15.0) / 100.0, 4),
                "cor": cor_deterministica(item["nome"]),
            }
        )

    # Multiplacas: desenha N balcões lado a lado (larguras de cada placa)
    placas = []
    if modulos_balcao_cm:
        x_acumulado = 0.0
        for largura in modulos_balcao_cm:
            placas.append(
                {
                    "largura_m": round(largura / 100.0, 4),
                    "profundidade_m": round(profundidade_balcao_cm / 100.0, 4),
                    "offset_x_m": round(x_acumulado / 100.0, 4),
                }
            )
            x_acumulado += largura + GAP_PLACAS_CM

    return {
        "template_path": template_path,
        "output_path": os.path.abspath(caminho_saida_png),
        "glb_dir": glb_dir,
        "balcao": {
            "largura_m": round(largura_balcao_cm / 100.0, 4),
            "profundidade_m": round(profundidade_balcao_cm / 100.0, 4),
            "altura_m": z_tampo_m,
            "espessura_tampo_m": round(espessura_tampo_cm / 100.0, 4),
        },
        "placas": placas,
        "camera": {
            "angulo_elevacao_graus": float(angulo_camera_graus),
            # Cotas projetam ~0,4 m além das faces do balcão: ocupação menor
            "fator_ocupacao": 0.7 if exibir_cotas else 0.9,
        },
        "cotas": {
            "exibir": bool(exibir_cotas),
            "modulos_m": [round(m / 100.0, 4) for m in (modulos_balcao_cm or [])],
        },
        "render": {
            "motor": "BLENDER_EEVEE_NEXT",
            "resolucao_x": int(resolucao[0]),
            "resolucao_y": int(resolucao[1]),
            "amostras": int(amostras),
        },
        "itens": itens_3d,
    }


# ---------------------------------------------------------------------------
# Execução headless
# ---------------------------------------------------------------------------
def extrair_metricas_blender(stdout):
    """Localiza a linha com o JSON de métricas do script do Blender no stdout.

    Quando ENABLE_RENDER_METRICS está ativo, o script imprime:
        [RENDER_METRICS_JSON] {"blender_version": ..., "init_sec": ..., ...}
    Retorna o dict ou None se o marcador não estiver presente.
    """
    for linha in stdout.splitlines():
        texto = linha.strip()
        if texto.startswith(MARCADOR_METRICAS):
            try:
                return json.loads(texto[len(MARCADOR_METRICAS):])
            except json.JSONDecodeError:
                return None
    return None


def _imprimir_log_metricas(coletor_metricas):
    """Imprime no console um resumo formatado das métricas coletadas."""
    interno = (coletor_metricas or {}).get("blender_interno") or {}
    print("\n--- [MÉTRICAS DE RENDER] ---")
    print(
        f"  json_build_sec:          "
        f"{coletor_metricas.get('json_build_sec', 0.0):.4f}"
    )
    total_sub = coletor_metricas.get("subprocess_total_sec")
    if total_sub is not None:
        print(f"  subprocess_total_sec:    {total_sub:.4f}")
    overhead = coletor_metricas.get("subprocess_overhead_sec")
    if overhead is not None:
        print(f"  subprocess_overhead_sec: {overhead:.4f}")
    else:
        print("  subprocess_overhead_sec: N/D")
    for chave, valor in interno.items():
        if chave.endswith("_sec"):
            print(f"  blender.{chave}: {valor:.4f}s")
        elif chave in ("peak_memory_mb", "cpu_percent"):
            print(f"  blender.{chave}: {valor}")
        else:
            print(f"  blender.{chave}: {valor}")
    print("--- [FIM MÉTRICAS] ---")


def renderizar_cena_3d(job, timeout_segundos=300, coletor_metricas=None):
    """Executa `blender -b -P <script> -- <job.json>` e retorna o PNG gerado.

    Quando `coletor_metricas` é um dict (ENABLE_RENDER_METRICS ativo), ele é
    preenchido in-place com as métricas do pipeline FastAPI:
        json_build_sec            -> tempo de gravação do render_job_*.json
        subprocess_total_sec      -> duração total do processo Blender
        subprocess_overhead_sec   -> spawn + carga de DLLs + teardown
        blender_interno           -> JSON de fases reportado pelo script Blender
    A flag ENABLE_RENDER_METRICS é repassada ao processo filho via
    `env=os.environ` (herança), ligando o profiler interno do script.

    Levanta:
        BlenderNaoEncontradoError: executável do Blender indisponível.
        FalhaRenderizacaoBlenderError: processo falhou ou PNG não foi gerado.
    """
    executavel = obter_executavel_blender()
    if not blender_disponivel():
        raise BlenderNaoEncontradoError(
            f"Executável do Blender não encontrado ('{executavel}'). "
            "Instale o Blender 4.2+ ou aponte a variável de ambiente "
            "BLENDER_PATH para o executável."
        )

    caminho_saida = os.path.abspath(job["output_path"])
    os.makedirs(os.path.dirname(caminho_saida), exist_ok=True)

    arquivo_job = tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", prefix="render_job_", delete=False, encoding="utf-8"
    )
    try:
        inicio_dump = time.perf_counter() if coletor_metricas is not None else None
        json.dump(job, arquivo_job, ensure_ascii=False, indent=2)
        arquivo_job.close()
        if coletor_metricas is not None:
            coletor_metricas["json_build_sec"] = coletor_metricas.get(
                "json_build_sec", 0.0
            ) + (time.perf_counter() - inicio_dump)

        comando = [
            executavel,
            "-b",
            "-P",
            CAMINHO_SCRIPT_BLENDER,
            "--",
            arquivo_job.name,
        ]
        # Backdoor de diagnóstico (test-only): RENDER_GPU_DEVICE=<index|hex> fixa
        # o dispositivo Vulkan do render (--gpu-device-no-fallback: falha rápido
        # se o dispositivo não existir). Útil para A/B de GPU vs software e para
        # confirmar o dispositivo real (consulte a métrica render_device).
        dispositivo_gpu = os.environ.get("RENDER_GPU_DEVICE", "").strip()
        if dispositivo_gpu:
            comando.extend(
                [
                    "--gpu-backend",
                    "vulkan",
                    "--gpu-device",
                    dispositivo_gpu,
                    "--gpu-device-no-fallback",
                ]
            )
        print(f" > Invocando Blender headless: {' '.join(comando)}")

        inicio_subprocesso = time.perf_counter() if coletor_metricas is not None else None
        try:
            resultado = subprocess.run(
                comando,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout_segundos,
                env=os.environ,
            )
        except FileNotFoundError as exc:
            raise BlenderNaoEncontradoError(
                f"Executável do Blender não encontrado ('{executavel}')."
            ) from exc
        except PermissionError as exc:
            raise BlenderNaoEncontradoError(
                f"Acesso negado (WinError 5) ao executar '{executavel}'. "
                "Verifique se BLENDER_PATH aponta para o arquivo blender.exe "
                "(e não para a pasta de instalação do Blender)."
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise FalhaRenderizacaoBlenderError(
                f"Blender excedeu o tempo limite de {timeout_segundos}s."
            ) from exc

        log_completo = f"{resultado.stdout}\n{resultado.stderr}".strip()

        print("\n--- [LOG DO BLENDER INÍCIO] ---")
        for linha in log_completo.splitlines():
            # Filtra ruídos internos do Blender e exibe os prints do seu script (iniciados com '>')
            if linha.strip().startswith(">") or "Error" in linha or "Warning" in linha:
                print(f"  {linha.strip()}")
        print("--- [LOG DO BLENDER FIM] ---\n")
        if resultado.returncode != 0:
            raise FalhaRenderizacaoBlenderError(
                f"Blender finalizou com código {resultado.returncode}.\n"
                f"Saída:\n{log_completo[-3000:]}"
            )

        if not os.path.exists(caminho_saida):
            raise FalhaRenderizacaoBlenderError(
                "Blender executou sem erros, mas o PNG não foi gerado em "
                f"'{caminho_saida}'.\nSaída:\n{log_completo[-3000:]}"
            )

        for linha in log_completo.splitlines():
            if MARCADOR_SUCESSO in linha:
                print(f" > {linha.strip()}")
                break

        if coletor_metricas is not None:
            subprocess_total = time.perf_counter() - inicio_subprocesso
            coletor_metricas["subprocess_total_sec"] = subprocess_total
            interno = extrair_metricas_blender(resultado.stdout)
            coletor_metricas["blender_interno"] = interno
            if interno and interno.get("total_script_sec") is not None:
                coletor_metricas["subprocess_overhead_sec"] = round(
                    subprocess_total - interno["total_script_sec"], 6
                )
            else:
                coletor_metricas["subprocess_overhead_sec"] = None
            _imprimir_log_metricas(coletor_metricas)

        return caminho_saida
    finally:
        try:
            os.unlink(arquivo_job.name)
        except OSError:
            pass
