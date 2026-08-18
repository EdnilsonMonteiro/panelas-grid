"""Telemetria opcional do pipeline de render (ENABLE_RENDER_METRICS).

Quando inativa, nenhuma chamada de timer é feita e nenhum arquivo é criado:
o fluxo de renderização permanece exatamente o original.

Marcador de stdout usado pelo wrapper (`blender_headless.py`): o JSON de
métricas é impresso com o prefixo `[RENDER_METRICS_JSON]`.
"""

import os
import sys
import time

import bpy

MARCADOR_METRICAS = "[RENDER_METRICS_JSON]"


def _metricas_ativas():
    valor = os.environ.get("ENABLE_RENDER_METRICS", "").strip().lower()
    return valor in ("true", "1", "yes")


METRICAS_ATIVAS = _metricas_ativas()
_INICIO_SCRIPT = time.perf_counter()
METRICAS = {}
_PROCESSO_MONITORADO = None  # psutil.Process usado para CPU (best-effort)
_CPU_INICIO = None  # (wall_clock, cpu_segundos) da medição nativa Win32

CHAVES_METRICAS_TEMPO = (
    "init_sec",
    "balcao_setup_sec",
    "food_allocation_sec",
    "boolean_operations_sec",
    "environment_and_dimensions_sec",
    "eevee_render_sec",
    "file_save_sec",
    "total_script_sec",
)

if METRICAS_ATIVAS:
    METRICAS.update({chave: 0.0 for chave in CHAVES_METRICAS_TEMPO})
    METRICAS["peak_memory_mb"] = 0.0
    METRICAS["cpu_percent"] = 0.0
    METRICAS["render_device"] = None


def _dispositivo_render():
    """Nome do dispositivo de renderização ativo (ex.: 'NVIDIA Corporation |
    NVIDIA GeForce RTX 4060 Ti'). Inicializa o contexto de GPU (best-effort);
    se falhar, retorna None e a métrica fica ausente. É o campo que prova se o
    render rodou em GPU de verdade ou em software (llvmpipe/WARP) num servidor
    sem GPU."""
    try:
        import gpu

        gpu.init()
        return f"{gpu.platform.vendor_get()} | {gpu.platform.renderer_get()}"
    except Exception:
        return None


def _registrar_metrica(chave, inicio):
    """Acumula a duração da fase `chave` em segundos (perf_counter)."""
    if METRICAS_ATIVAS:
        METRICAS[chave] += time.perf_counter() - inicio


def _amostrar_memoria_pico():
    """Mede o pico de RAM (RSS) funcionando nativamente em Windows e Linux,
    sem depender obrigatoriamente do pacote 'psutil' instalado no Blender.
    """
    if not METRICAS_ATIVAS:
        return

    rss_mb = 0.0

    # 1. TENTATIVA COM PSUTIL (Se instalado no Python do Blender)
    try:
        import psutil

        processo = psutil.Process(os.getpid())
        # Inclui a memória de processos filhos criados pelo Blender, se houver
        mem_bytes = processo.memory_info().rss
        for filho in processo.children(recursive=True):
            try:
                mem_bytes += filho.memory_info().rss
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        rss_mb = mem_bytes / (1024.0 * 1024.0)
    except Exception:
        pass

    # 2. FALLBACK PARA WINDOWS (Win32 API nativa via ctypes - Sem instalar nada)
    #
    # IMPORTANTE: ctypes.windll não declara argtypes/restype por padrão, então
    # o HANDLE retornado por GetCurrentProcess era truncado para 32 bits e a
    # chamada GetProcessMemoryInfo falhava (BOOL = 0), mantendo a métrica em
    # 0.0. Aqui as assinaturas são declaradas explicitamente.
    if rss_mb == 0.0 and os.name == "nt":
        try:
            import ctypes
            from ctypes import wintypes

            class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
                _fields_ = [
                    ("cb", wintypes.DWORD),
                    ("PageFaultCount", wintypes.DWORD),
                    ("PeakWorkingSetSize", ctypes.c_size_t),
                    ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t),
                    ("PeakPagefileUsage", ctypes.c_size_t),
                ]

            psapi = ctypes.WinDLL("psapi", use_last_error=True)
            GetProcessMemoryInfo = psapi.GetProcessMemoryInfo
            GetProcessMemoryInfo.argtypes = [
                wintypes.HANDLE,
                ctypes.POINTER(PROCESS_MEMORY_COUNTERS),
                wintypes.DWORD,
            ]
            GetProcessMemoryInfo.restype = wintypes.BOOL

            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            GetCurrentProcess = kernel32.GetCurrentProcess
            GetCurrentProcess.restype = wintypes.HANDLE

            pmc = PROCESS_MEMORY_COUNTERS()
            pmc.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS)
            handle = GetCurrentProcess()

            if GetProcessMemoryInfo(handle, ctypes.byref(pmc), pmc.cb):
                # PeakWorkingSetSize armazena o PICO MÁXIMO de RAM que o processo já atingiu
                rss_mb = pmc.PeakWorkingSetSize / (1024.0 * 1024.0)
        except Exception:
            pass

    # 3. FALLBACK PARA LINUX / POSIX (via módulo 'resource')
    if rss_mb == 0.0:
        try:
            import resource

            pico_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            # No Linux, ru_maxrss é retornado em Kilobytes
            # No macOS (Darwin), é retornado em Bytes
            divisor = 1024.0 if sys.platform != "darwin" else (1024.0 * 1024.0)
            rss_mb = pico_kb / divisor
        except Exception:
            pass

    # 4. FALLBACK FINAL: Memória da cena do próprio Blender (bpy.app.memory)
    if rss_mb == 0.0:
        try:
            # bpy.app.memory.peak_usage() indica o pico de RAM alocado para geometria/shaders
            rss_mb = bpy.app.memory.peak_usage() / (1024.0 * 1024.0)
        except Exception:
            pass

    # Atualiza o pico global armazenado
    if rss_mb > 0.0:
        METRICAS["peak_memory_mb"] = max(METRICAS.get("peak_memory_mb", 0.0), rss_mb)


def _tempo_cpu_processo():
    """Tempo de CPU acumulado do processo (kernel+user) em segundos, sem
    psutil: Win32 GetProcessTimes. Retorna None se indisponível ou falhar
    (não-Windows ou erro)."""
    if os.name != "nt":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        class FILETIME(ctypes.Structure):
            _fields_ = [
                ("dwLowDateTime", wintypes.DWORD),
                ("dwHighDateTime", wintypes.DWORD),
            ]

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        GetProcessTimes = kernel32.GetProcessTimes
        GetProcessTimes.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(FILETIME),
            ctypes.POINTER(FILETIME),
            ctypes.POINTER(FILETIME),
            ctypes.POINTER(FILETIME),
        ]
        GetProcessTimes.restype = wintypes.BOOL
        GetCurrentProcess = kernel32.GetCurrentProcess
        GetCurrentProcess.restype = wintypes.HANDLE

        criacao = FILETIME()
        saida = FILETIME()
        kernel = FILETIME()
        usuario = FILETIME()
        if not GetProcessTimes(
            GetCurrentProcess(),
            ctypes.byref(criacao),
            ctypes.byref(saida),
            ctypes.byref(kernel),
            ctypes.byref(usuario),
        ):
            return None

        def _para_segundos(ft):
            # FILETIME: 100-ns unidades
            return (ft.dwHighDateTime * 4294967296 + ft.dwLowDateTime) / 1.0e7

        return _para_segundos(kernel) + _para_segundos(usuario)
    except Exception:
        return None


def _iniciar_cpu():
    """Prepara a medição de CPU do processo Blender.

    Prefere psutil (funciona em Windows/Linux, mede % sobre um núcleo e pode
    passar de 100% em multi-core); sem psutil, usa a medição nativa Win32
    (GetProcessTimes) entre o início e o fim do render."""
    global _PROCESSO_MONITORADO, _CPU_INICIO
    if not METRICAS_ATIVAS:
        return
    _CPU_INICIO = None
    try:
        import psutil

        _PROCESSO_MONITORADO = psutil.Process(os.getpid())
        _PROCESSO_MONITORADO.cpu_percent(interval=None)
        return
    except Exception:
        _PROCESSO_MONITORADO = None

    inicio_cpu = _tempo_cpu_processo()
    if inicio_cpu is not None:
        _CPU_INICIO = (time.perf_counter(), inicio_cpu)


def _finalizar_cpu():
    """Retorna o % de CPU do processo Blender desde `_iniciar_cpu`."""
    if _PROCESSO_MONITORADO is not None:
        try:
            return _PROCESSO_MONITORADO.cpu_percent(interval=None)
        except Exception:
            return 0.0
    if _CPU_INICIO is None:
        return 0.0
    fim_cpu = _tempo_cpu_processo()
    if fim_cpu is None:
        return 0.0
    parede0, cpu0 = _CPU_INICIO
    parede = time.perf_counter() - parede0
    if parede <= 0.0:
        return 0.0
    # Mesma semântica do psutil: % em relação a UM núcleo (pode passar de 100)
    return round((fim_cpu - cpu0) / parede * 100.0, 1)