"""Exportador do PDF 'Proposta Comercial' (A4 Landscape, página única).

Layout visual replicando o protótipo comercial:
    A. Cabeçalho (logo + PROPOSTA COMERCIAL + cliente/data/medidas)
    B. Bloco central (render 3D da Opção 1 + caixa "Detalhes Importantes")
    C. Bloco inferior esquerdo (cards PISTA AQUECIDA / PISTA FRIA)
    D. Bloco inferior direito ("Outras Opções de Layout" em plantas 2D)
    E. Rodapé ("Sugestão de Uso")

Sem substituir o PDF/PPTX de opções: é uma exportação adicional.
"""

import os
import re
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph

from ._imagens import caminho_panela_otimizado
from .pdf import ExportadorPDF

ARQUIVO_ATUAL = Path(__file__).resolve()

PASTA_RAIZ_PROJETO = next(
    p for p in ARQUIVO_ATUAL.parents if (p / "assets").exists() or (p / "src").exists()
)

PASTA_ASSETS = PASTA_RAIZ_PROJETO / "assets"

# ─────────────────────────────────────────────────────
# PALETA (Protótipo comercial)
# ─────────────────────────────────────────────────────
GRAFITE = colors.HexColor("#1F2937")
TEXTO = colors.HexColor("#374151")
CINZA_CLARO = colors.HexColor("#F3F4F6")
BORDA_CINZA = colors.HexColor("#D1D5DB")
BRANCO = colors.white

LARANJA = colors.HexColor("#EA580C")      # Pista Aquecida
LARANJA_FUNDO = colors.HexColor("#FFF1E6")
AZUL = colors.HexColor("#0E7490")         # Pista Fria (azul/água)
AZUL_FUNDO = colors.HexColor("#E6F5F8")

GAP_PLACAS_CM = 1.0  # espaçamento entre placas (multiplacas)

# ─────────────────────────────────────────────────────
# ESTILOS DE TEXTO
# ─────────────────────────────────────────────────────
ESTILO_TITULO = ParagraphStyle(
    "titulo", fontName="Helvetica-Bold", fontSize=26, leading=30, textColor=GRAFITE
)
ESTILO_INFO = ParagraphStyle(
    "info", fontName="Helvetica", fontSize=11, leading=16, textColor=TEXTO
)
ESTILO_SUB_CAIXA = ParagraphStyle(
    "subcaixa",
    fontName="Helvetica-Bold",
    fontSize=12,
    leading=15,
    textColor=BRANCO,
)
ESTILO_DETALHES = ParagraphStyle(
    "detalhes",
    fontName="Helvetica",
    fontSize=10.5,
    leading=17,
    textColor=TEXTO,
    leftIndent=10,
)
ESTILO_ITEM_PISTA = ParagraphStyle(
    "itempista", fontName="Helvetica", fontSize=9.5, leading=15, textColor=TEXTO
)
ESTILO_SUGESTAO = ParagraphStyle(
    "sugestao", fontName="Helvetica", fontSize=10.5, leading=16, textColor=TEXTO
)


def _normalizar_modelo(nome: str) -> str:
    """Agrega variantes no mesmo modelo para a composição das pistas.

    - Remove o sufixo de rotação " (R)".
    - Remove o contador numérico final (ex.: "Arroz 1" -> "Arroz").
    """
    nome = (nome or "").strip()
    nome = re.sub(r"\s*\(R\)\s*$", "", nome)
    nome = re.sub(r"\s+\d+\s*$", "", nome)
    return nome or "Peça"


def _nome_e_tamanho(item, diametro_panela):
    """Devolve (nome do modelo, tamanho w×h) de um item alocado.

    Panelas redondas usam o nome do catálogo de panelas (ex.: "Panela 34"),
    mapeado pelo diâmetro alocado; cubas retangulares mantêm o nome do item.
    """
    w = int(round(item.get("w", 0)))
    h = int(round(item.get("h", 0)))
    tamanho = f"{w}x{h}"

    if item.get("formato") == "circulo":
        d = max(w, h)
        nome = diametro_panela.get(float(d))
        if not nome:
            nome = f"Panela {d:.0f}"
        return nome, tamanho

    return _normalizar_modelo(item.get("nome", "")), tamanho


def _composicao(pedido) -> Dict[str, List[str]]:
    """Agrupa os modelos alocados por pista (quente/fria), somando as placas."""
    diametro_panela: Dict[float, str] = {}
    contagem: Dict[str, Counter] = {"quente": Counter(), "fria": Counter()}

    for modulo in pedido.modulos:
        secao_pista = {s.nome: s.pista for s in modulo.secoes}

        # Mapa diâmetro -> nome da panela redonda (a partir do catálogo da seção)
        for secao in modulo.secoes:
            catalogo_panelas = getattr(secao, "catalogo_panelas", None) or []
            for item_cat in catalogo_panelas:
                d = item_cat.get("diametro") or item_cat.get("w") or 0
                if d:
                    diametro_panela[float(d)] = (
                        item_cat.get("nome") or f"Panela {float(d):.0f}"
                    )

        for item in modulo.engine.itens:
            pista = secao_pista.get(item.get("secao"), "quente")
            contagem[pista][_nome_e_tamanho(item, diametro_panela)] += 1

    def _formatar(pista: str) -> List[str]:
        return [
            f"{n}x {nome} — {tamanho}"
            for (nome, tamanho), n in contagem[pista].most_common()
        ]

    return {"quente": _formatar("quente"), "fria": _formatar("fria")}


def _resumo_pistas(pedido) -> Dict[str, Any]:
    """Tamanho (LxP) e quantidade de travessas de cada pista, e o total.

    O comprimento de cada pista é a extensão real ocupada pelos itens somando
    todas as placas (as placas são dispostas lado a lado com um gap).
    Pistas sem itens não são incluídas no resumo.
    """
    x_min_total: Dict[str, Optional[float]] = {"quente": None, "fria": None}
    x_max_total: Dict[str, Optional[float]] = {"quente": None, "fria": None}
    contagem: Dict[str, int] = {"quente": 0, "fria": 0}
    profundidade = 0.0

    x_deslocamento = 0.0
    for modulo in pedido.modulos:
        profundidade = max(profundidade, modulo.engine.P)
        secao_pista = {s.nome: s.pista for s in modulo.secoes}
        for item in modulo.engine.itens:
            pista = secao_pista.get(item.get("secao"), "quente")
            contagem[pista] += 1
            x0 = x_deslocamento + item["x"]
            x1 = x_deslocamento + item["x"] + item["w"]
            if x_min_total[pista] is None or x0 < x_min_total[pista]:
                x_min_total[pista] = x0
            if x_max_total[pista] is None or x1 > x_max_total[pista]:
                x_max_total[pista] = x1
        x_deslocamento += modulo.engine.L + GAP_PLACAS_CM

    resumo: Dict[str, Any] = {}
    for pista in ("quente", "fria"):
        if x_min_total[pista] is None:
            continue
        compr = x_max_total[pista] - x_min_total[pista]
        resumo[pista] = {
            "tamanho": f"{compr:.0f}x{profundidade:.0f}",
            "qtd": contagem[pista],
        }

    resumo["total"] = contagem["quente"] + contagem["fria"]
    return resumo


def _dimensoes_utilizadas(pedido) -> List[Tuple[str, int, int, int]]:
    """Dimensões únicas das travessas, da menor para a maior (todas as placas).

    Retangulares são deduplicadas por rotação (21x13 ≡ 13x21), somando a
    quantidade; mantém-se a primeira orientação encontrada. A ordenação compara
    o primeiro número (à esquerda de 'x') e, em caso de empate, o segundo.
    """
    contagem: Counter = Counter()
    representacao: Dict[Any, Tuple[str, int, int]] = {}

    def _chave(fmt: str, w: int, h: int) -> Tuple[Any, ...]:
        if fmt == "circulo":
            d = max(w, h)
            return ("circulo", d)
        return ("retangulo", min(w, h), max(w, h))

    for modulo in pedido.modulos:
        for item in modulo.engine.itens:
            fmt = item.get("formato", "retangulo")
            w = int(round(item.get("w", 0)))
            h = int(round(item.get("h", 0)))
            if w > 0 and h > 0:
                chave = _chave(fmt, w, h)
                contagem[chave] += 1
                representacao.setdefault(
                    chave,
                    (fmt, max(w, h), max(w, h))
                    if fmt == "circulo"
                    else (fmt, w, h),
                )

    resultado = [
        (fmt, w, h, contagem[chave])
        for chave, (fmt, w, h) in representacao.items()
    ]
    resultado.sort(key=lambda c: (c[1], c[2]))
    return resultado


class ExportadorProposta:
    @staticmethod
    def gerar(dados: Dict[str, Any], opcoes: List[Dict[str, Any]], nome_arquivo: str):
        """Gera o PDF da proposta comercial em página vertical extensa.

        A largura segue o A4 landscape; a altura é calculada para acomodar
        todos os blocos (header, central, pistas, dimensões, sugestão e resumo).

        `dados`: nome_cliente, data, largura_cm, profundidade_cm (da Opção 1).
        `opcoes`: lista de {numero, titulo, pedido (ComposicaoBalcao),
                            imagem_3d (caminho PNG | None)} — opcoes[0] é a Opção 1.
        """
        W = landscape(A4)[0]
        M = 1.2 * cm

        ALT_HEADER = 130
        ALT_CENTRAL = 200
        ALT_INFERIOR = 150
        ALT_DIMENSOES = 110
        ALT_SUGESTAO = 95
        ALT_RESUMO = 70
        GAP = 16
        TOPO = 36
        BASE = 40

        H = (
            TOPO
            + ALT_HEADER
            + GAP
            + ALT_CENTRAL
            + GAP
            + ALT_INFERIOR
            + GAP
            + ALT_DIMENSOES
            + GAP
            + ALT_SUGESTAO
            + GAP
            + ALT_RESUMO
            + BASE
        )

        c = canvas.Canvas(nome_arquivo, pagesize=(W, H))

        def y_topo(offset: float) -> float:
            return H - offset

        cursor = TOPO

        # ───────────────────────────────────────
        # A. CABEÇALHO
        # ───────────────────────────────────────
        caminho_logo = os.path.join(PASTA_ASSETS, "logo.png")
        if os.path.exists(caminho_logo):
            try:
                c.drawImage(
                    caminho_logo,
                    M,
                    y_topo(76),
                    width=250,
                    height=62,
                    preserveAspectRatio=True,
                    mask="auto",
                )
            except Exception as e:  # imagem corrompida não deve derrubar o PDF
                print(f" > [Proposta] Falha ao desenhar logo: {e}")

        titulo = Paragraph("PROPOSTA COMERCIAL", ESTILO_TITULO)
        xc_titulo = W / 2 + M / 2
        titulo.wrapOn(c, W / 2 - M, 40)
        titulo.drawOn(c, xc_titulo, y_topo(52))

        x_inf = W / 2 + M / 2

        # Cliente e Data na mesma linha (com distância); quebra se o nome for longo.
        # Bloco ancorado pela base acima da linha divisória -> nunca a cruza.
        texto_info = (
            f"Cliente: {dados.get('nome_cliente', '—')}&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;"
            f"Data: {dados.get('data', '—')}<br/>"
            f"Medidas do Balcão: L = {dados.get('largura_cm', 0):.0f} cm | "
            f"P = {dados.get('profundidade_cm', 0):.0f} cm"
        )
        par_info = Paragraph(texto_info, ESTILO_INFO)
        largura_info = W - M - x_inf
        par_info.wrapOn(c, largura_info, 200)
        par_info.drawOn(c, x_inf, y_topo(97))

        c.setStrokeColor(BORDA_CINZA)
        c.setLineWidth(1)
        c.line(M, y_topo(102), W - M, y_topo(102))

        cursor += ALT_HEADER + GAP

        # ───────────────────────────────────────
        # B. BLOCO CENTRAL (3D + Detalhes)
        # ───────────────────────────────────────
        x_esq = M
        w_meio = W / 2 - M - 8  # usado no bloco inferior (C/D) — não alterar
        y_main_topo = y_topo(cursor)
        y_main_base = y_topo(cursor + ALT_CENTRAL)
        h_main = y_main_topo - y_main_base

        # Bloco central: 3D ocupa 80% e "Detalhes Importantes" 20%
        GAP_MEIO = 16
        w_3d = (W - 2 * M - GAP_MEIO) * 0.8
        w_det = (W - 2 * M - GAP_MEIO) * 0.2
        x_dir = x_esq + w_3d + GAP_MEIO

        # --- B1. Render 3D da Opção 1 ---
        ExportadorProposta._caixa(c, x_esq, y_main_base, w_3d, h_main)
        ExportadorProposta._badge(
            c, x_esq, y_main_topo, "Visualização 3D - Opção 1", GRAFITE
        )
        # Área da imagem abaixo do badge (reserva ~28pt no topo da caixa)
        y_img_topo = y_main_topo - 28
        y_img_base = y_main_base + 8
        h_img = y_img_topo - y_img_base
        imagem_3d = opcoes[0].get("imagem_3d") if opcoes else None
        if imagem_3d and os.path.exists(imagem_3d):
            try:
                c.drawImage(
                    imagem_3d,
                    x_esq + 8,
                    y_img_base,
                    w_3d - 16,
                    h_img,
                    preserveAspectRatio=True,
                    mask="auto",
                )
            except Exception as e:
                print(f" > [Proposta] Falha ao embutir render 3D: {e}")
                ExportadorProposta._placeholder_3d(
                    c, x_esq, y_img_base, w_3d, h_img
                )
        else:
            ExportadorProposta._placeholder_3d(c, x_esq, y_img_base, w_3d, h_img)

        # --- B2. Caixa "Detalhes Importantes" ---
        ExportadorProposta._caixa(c, x_dir, y_main_base, w_det, h_main, preencher=True)
        ExportadorProposta._badge(
            c, x_dir, y_main_topo, "Detalhes Importantes", GRAFITE
        )
        bullets = [
            "Equipamentos portáteis e discretos",
            "Instalação rápida e prática",
            "Ideal para autosserviço ou atendimento assistido",
            "Visual leve, elegante e aconchegante",
        ]
        est_det = ParagraphStyle(
            "detalhes_estreito",
            fontName="Helvetica",
            fontSize=9,
            leading=13,
            textColor=TEXTO,
            leftIndent=8,
        )
        y_b = y_main_topo - 30
        for texto in bullets:
            par = Paragraph(f"•&nbsp;&nbsp;{texto}", est_det)
            _, par_h = par.wrapOn(c, w_det - 20, 200)
            par.drawOn(c, x_dir + 10, y_b - par_h)
            y_b -= par_h + 5

        cursor += ALT_CENTRAL + GAP

        # ───────────────────────────────────────
        # C/D. BLOCO INFERIOR (Pistas + Outras Opções)
        # ───────────────────────────────────────
        y_bot_topo = y_topo(cursor)
        y_bot_base = y_topo(cursor + ALT_INFERIOR)
        h_bot = y_bot_topo - y_bot_base

        outras_opcoes = opcoes[1:]
        tem_outras = len(outras_opcoes) > 0

        if tem_outras:
            # Esquerda: composição das pistas (cards); Direita: outras opções
            x_dir_inf = W / 2 + 8  # divisão 50/50 independente do bloco central
            w_comp = w_meio
            ExportadorProposta._desenhar_pistas(
                c, x_esq, y_bot_base, w_comp, h_bot, opcoes[0]["pedido"]
            )
            ExportadorProposta._desenhar_outras_opcoes(
                c, x_dir_inf, y_bot_base, w_meio, h_bot, outras_opcoes
            )
        else:
            # Regra 1: sem outras opções, as pistas expandem para preencher
            w_comp = W - 2 * M
            ExportadorProposta._desenhar_pistas(
                c, x_esq, y_bot_base, w_comp, h_bot, opcoes[0]["pedido"]
            )

        cursor += ALT_INFERIOR + GAP

        # ───────────────────────────────────────
        # DIMENSÕES DAS TRAVESSAS UTILIZADAS
        # ───────────────────────────────────────
        y_dim_topo = y_topo(cursor)
        y_dim_base = y_topo(cursor + ALT_DIMENSOES)
        ExportadorProposta._desenhar_dimensoes(
            c,
            M,
            y_dim_base,
            W - 2 * M,
            y_dim_topo - y_dim_base,
            _dimensoes_utilizadas(opcoes[0]["pedido"]),
        )

        cursor += ALT_DIMENSOES + GAP

        # ───────────────────────────────────────
        # E. RODAPÉ — SUGESTÃO DE USO
        # ───────────────────────────────────────
        y_foot_topo = y_topo(cursor)
        y_foot_base = y_topo(cursor + ALT_SUGESTAO)
        ExportadorProposta._caixa(
            c, M, y_foot_base, W - 2 * M, y_foot_topo - y_foot_base, preencher=True
        )
        c.setFillColor(GRAFITE)
        c.setFont("Helvetica-Bold", 13)
        c.drawString(M + 14, y_foot_topo - 22, "Sugestão de Uso")
        texto_sugestao = (
            "Para manter a elegância do buffet e a fluidez do atendimento, "
            "recomendamos dispor os pratos e talheres no início da pista aquecida, "
            "seguidos pelas opções quentes principais. A pista fria deve comportar "
            "saladas, molhos e acompanhamentos frescos de forma simétrica e acessível."
        )
        par = Paragraph(texto_sugestao, ESTILO_SUGESTAO)
        par.wrapOn(c, W - 2 * M - 28, 200)
        par.drawOn(c, M + 14, y_foot_base + 12)

        cursor += ALT_SUGESTAO + GAP

        # ───────────────────────────────────────
        # RESUMO DAS PISTAS (box final, largura total)
        # ───────────────────────────────────────
        y_resumo_topo = y_topo(cursor)
        y_resumo_base = y_topo(cursor + ALT_RESUMO)
        ExportadorProposta._desenhar_resumo_pistas(
            c,
            M,
            y_resumo_base,
            W - 2 * M,
            y_resumo_topo - y_resumo_base,
            _resumo_pistas(opcoes[0]["pedido"]),
        )

        c.showPage()
        c.save()
        print(f" > Proposta comercial gerada: '{nome_arquivo}'")

    # ─────────────────────────────────────
    # HELPERS DE DESENHO
    # ─────────────────────────────────────
    @staticmethod
    def _caixa(c, x, y, w, h, preencher=False):
        """Desenha uma caixa com cantos arredondados (borda fina e elegante)."""
        c.setStrokeColor(BORDA_CINZA)
        c.setLineWidth(0.8)
        if preencher:
            c.setFillColor(CINZA_CLARO)
            c.roundRect(x, y, w, h, 6, fill=1, stroke=1)
        else:
            c.setFillColor(BRANCO)
            c.roundRect(x, y, w, h, 6, fill=1, stroke=1)

    @staticmethod
    def _baseline_centrada(box_bottom, box_height, font_name, font_size):
        """Baseline para o texto ficar verticalmente centralizado na caixa."""
        asc = pdfmetrics.getAscent(font_name) / 1000.0 * font_size
        desc = abs(pdfmetrics.getDescent(font_name)) / 1000.0 * font_size
        return box_bottom + (box_height - (asc + desc)) / 2 + desc

    @staticmethod
    def _badge(c, x, y_topo, texto, cor):
        """Etiqueta sobre o topo de uma caixa."""
        c.setFillColor(cor)
        w_texto = 8 + c.stringWidth(texto, "Helvetica-Bold", 10) + 8
        h_texto = 18
        c.roundRect(x + 10, y_topo - h_texto - 4, w_texto, h_texto, 4, fill=1, stroke=0)
        c.setFillColor(BRANCO)
        c.setFont("Helvetica-Bold", 10)
        baseline = ExportadorProposta._baseline_centrada(
            y_topo - h_texto - 4, h_texto, "Helvetica-Bold", 10
        )
        c.drawCentredString(x + 10 + w_texto / 2, baseline, texto)

    @staticmethod
    def _placeholder_3d(c, x, y, w, h):
        c.setFillColor(CINZA_CLARO)
        c.roundRect(x + 8, y + 8, w - 16, h - 16, 6, fill=1, stroke=0)
        c.setFillColor(colors.HexColor("#9CA3AF"))
        c.setFont("Helvetica", 11)
        c.drawCentredString(x + w / 2, y + h / 2, "Visualização 3D indisponível")

    @staticmethod
    def _desenhar_pistas(c, x, y, w, h, pedido):
        """Cards PISTA AQUECIDA / PISTA FRIA (só as pistas que possuem itens).

        Se apenas uma pista tiver itens, o card ocupa a largura disponível.
        """
        composicao = _composicao(pedido)
        gap = 12

        cards = []
        if composicao["quente"]:
            cards.append(("PISTA AQUECIDA", LARANJA, LARANJA_FUNDO, composicao["quente"]))
        if composicao["fria"]:
            cards.append(("PISTA FRIA", AZUL, AZUL_FUNDO, composicao["fria"]))
        if not cards:
            return

        w_card = (w - gap * (len(cards) - 1)) / len(cards)

        def desenhar_card(xc, largura, titulo, cor, cor_fundo, itens):
            c.setFillColor(cor_fundo)
            c.setStrokeColor(cor)
            c.setLineWidth(0.8)
            c.roundRect(xc, y, largura, h, 6, fill=1, stroke=1)
            # Título do card
            c.setFillColor(cor)
            c.roundRect(xc + 10, y + h - 26, largura - 20, 20, 4, fill=1, stroke=0)
            c.setFillColor(BRANCO)
            c.setFont("Helvetica-Bold", 10.5)
            baseline_titulo = ExportadorProposta._baseline_centrada(
                y + h - 26, 20, "Helvetica-Bold", 10.5
            )
            c.drawCentredString(xc + largura / 2, baseline_titulo, titulo)
            # Itens
            c.setFillColor(TEXTO)
            c.setFont("Helvetica", 9.5)
            limite = max(3, int((h - 44) / 15))
            linhas = itens[:limite]
            if len(itens) > limite:
                linhas.append("…")
            yy = y + h - 38
            for item in linhas:
                par = Paragraph(item, ESTILO_ITEM_PISTA)
                _, ph = par.wrapOn(c, largura - 20, 200)
                par.drawOn(c, xc + 12, yy - ph)
                yy -= ph + 4

        for indice, (titulo, cor, cor_fundo, itens) in enumerate(cards):
            desenhar_card(
                x + indice * (w_card + gap), w_card, titulo, cor, cor_fundo, itens
            )

    @staticmethod
    def _desenhar_outras_opcoes(c, x, y, w, h, outras_opcoes):
        """Miniaturas em planta baixa 2D das opções alternativas."""
        c.setStrokeColor(BORDA_CINZA)
        c.setLineWidth(0.8)
        c.setFillColor(BRANCO)
        c.roundRect(x, y, w, h, 6, fill=1, stroke=1)

        c.setFillColor(GRAFITE)
        c.setFont("Helvetica-Bold", 11)
        c.drawString(x + 12, y + h - 22, "Outras Opções de Layout")

        area_y = y + 10
        area_h = h - 42

        visiveis = outras_opcoes[:3]
        pad = 8
        if len(visiveis) == 1:
            larguras = [w - 2 * pad]
        elif len(visiveis) == 2:
            larguras = [(w - 3 * pad) / 2] * 2
        else:
            larguras = [(w - 4 * pad) / 3] * 3

        xx = x + pad
        for i, opcao in enumerate(visiveis):
            ExportadorProposta._desenhar_planta_2d(
                c,
                opcao["pedido"],
                xx,
                area_y,
                larguras[i],
                area_h,
                f"Opção {opcao['numero']}",
            )
            xx += larguras[i] + pad

        if len(outras_opcoes) > 3:
            c.setFillColor(colors.HexColor("#6B7280"))
            c.setFont("Helvetica-Bold", 10)
            c.drawCentredString(
                x + w / 2,
                area_y - 2,
                f"+{len(outras_opcoes) - 3} opção(ões) adicionais",
            )

    @staticmethod
    def _desenhar_planta_2d(c, pedido, x, y, w, h, rotulo):
        """Desenha a planta baixa 2D de uma opção dentro de um card miniatura.

        Reutiliza a lógica de desenho do balcão + panelas de ExportadorPDF
        (imagens de assets/), sem cabeçalho/cotas.
        """
        c.setFillColor(BRANCO)
        c.setStrokeColor(BORDA_CINZA)
        c.setLineWidth(0.8)
        c.roundRect(x, y, w, h, 4, fill=1, stroke=1)

        c.setFillColor(GRAFITE)
        c.setFont("Helvetica-Bold", 9)
        c.drawCentredString(x + w / 2, y + h - 13, rotulo)

        modulos = pedido.modulos
        if not modulos:
            return
        L_total = sum(m.engine.L for m in modulos) + GAP_PLACAS_CM * (len(modulos) - 1)
        P_max = max(m.engine.P for m in modulos)
        if L_total <= 0 or P_max <= 0:
            return

        pad = 6
        util_w = w - 2 * pad
        util_h = h - 20 - pad
        escala = min(util_w / (L_total * cm), util_h / (P_max * cm))
        plan_w = L_total * cm * escala
        plan_h = P_max * cm * escala
        ox = x + (w - plan_w) / 2
        oy = y + pad

        x_atual = ox
        for modulo in modulos:
            largura_placa = modulo.engine.L * cm * escala
            ExportadorPDF._desenhar_balcao(
                c,
                modulo,
                x_atual,
                oy,
                escala,
                exibir_texto=True,
                tamanho_texto=5.5,
            )
            x_atual += largura_placa + GAP_PLACAS_CM * cm * escala

    @staticmethod
    def _desenhar_dimensoes(c, x, y, w, h, dims):
        """Box 'Dimensões das travessas utilizadas' com imagem de cada travessa."""
        ExportadorProposta._caixa(c, x, y, w, h, preencher=True)
        c.setFillColor(GRAFITE)
        c.setFont("Helvetica-Bold", 12)
        c.drawString(x + 14, y + h - 22, "Dimensões das travessas utilizadas")

        if not dims:
            c.setFillColor(colors.HexColor("#9CA3AF"))
            c.setFont("Helvetica", 10)
            c.drawString(x + 14, y + 18, "Nenhuma travessa alocada.")
            return

        visiveis = dims[:8]
        pad = 10
        n = len(visiveis)
        larg_cel = (w - 2 * pad - pad * (n - 1)) / n
        x0 = x + pad
        area_topo = y + h - 34
        area_base = y + 10
        area_h = area_topo - area_base

        max_w = larg_cel - 16
        max_h = area_h - 22
        max_dw = max((d[1] for d in visiveis), default=1)
        max_dh = max((d[2] for d in visiveis), default=1)
        escala = min(max_w / max_dw, max_h / max_dh)

        for i, (fmt, dw, dh, _qtd) in enumerate(visiveis):
            cx = x0 + i * (larg_cel + pad) + larg_cel / 2

            # Medida da travessa (diâmetro nas redondas, WxH nas retangulares)
            medida = f"{dw}" if fmt == "circulo" else f"{dw}x{dh}"
            c.setFillColor(TEXTO)
            c.setFont("Helvetica-Bold", 10)
            c.drawCentredString(cx, area_topo - 12, medida)

            # Imagem da travessa abaixo da medida, na proporção real (dw:dh),
            # com escala única para todas as travessas do box.
            dw_im = dw * escala
            dh_im = dh * escala
            imagem = "panela_redonda.png" if fmt == "circulo" else "panela_retangular.png"
            caminho = caminho_panela_otimizado(imagem)
            if os.path.exists(caminho):
                try:
                    c.drawImage(
                        caminho,
                        cx - dw_im / 2,
                        area_base,
                        dw_im,
                        dh_im,
                        mask="auto",
                    )
                except Exception as e:
                    print(f" > [Proposta] Falha ao desenhar travessa {medida}: {e}")
            else:
                c.setFillColor(CINZA_CLARO)
                c.rect(cx - dw_im / 2, area_base, dw_im, dh_im, fill=1, stroke=0)

        if len(dims) > 8:
            c.setFillColor(colors.HexColor("#6B7280"))
            c.setFont("Helvetica-Bold", 10)
            c.drawCentredString(x + w / 2, y + 12, f"+{len(dims) - 8} dimensões adicionais")

    @staticmethod
    def _desenhar_resumo_pistas(c, x, y, w, h, resumo):
        """Box final (largura total) com tamanho e nº de travessas de cada pista.

        Cada pista aparece como "[ícone] Pista Aquecida (LxP): N travessas",
        separadas por "|", com o Total ao final. Pistas sem itens não aparecem.
        """
        ExportadorProposta._caixa(c, x, y, w, h, preencher=True)

        ICONE = 18
        GAP_ICONE = 7
        GAP = 14

        def _rotulo(pista: str) -> str:
            nome = "Pista Aquecida" if pista == "quente" else "Pista Fria"
            tam = resumo.get(pista, {}).get("tamanho")
            qtd = resumo.get(pista, {}).get("qtd", 0)
            plural = "s" if qtd != 1 else ""
            if tam:
                return f"{nome} ({tam}): {qtd} travessa{plural}"
            return f"{nome}: {qtd} travessa{plural}"

        total = resumo.get("total", 0)
        plural = "s" if total != 1 else ""
        texto_total = f"Total: {total} travessa{plural}"

        c.setFont("Helvetica-Bold", 11)
        separador = "|"
        w_sep = c.stringWidth(separador, "Helvetica-Bold", 11)
        w_total = c.stringWidth(texto_total, "Helvetica-Bold", 11)

        pistas = [p for p in ("quente", "fria") if p in resumo]
        larguras = {p: c.stringWidth(_rotulo(p), "Helvetica-Bold", 11) for p in pistas}

        total_w = (
            sum(ICONE + GAP_ICONE + larguras[p] for p in pistas)
            + w_total
            + len(pistas) * (w_sep + 2 * GAP)
        )
        x0 = x + max(14, (w - total_w) / 2)
        cy = y + h / 2
        baseline = ExportadorProposta._baseline_centrada(y, h, "Helvetica-Bold", 11)
        cor_sep = colors.HexColor("#9CA3AF")

        xc = x0
        for pista in pistas:
            if pista == "quente":
                ExportadorProposta._icone_pista_aquecida(c, xc + ICONE / 2, cy, size=ICONE)
                c.setFillColor(LARANJA)
            else:
                ExportadorProposta._icone_pista_fria(c, xc + ICONE / 2, cy, size=ICONE)
                c.setFillColor(AZUL)

            x_texto = xc + ICONE + GAP_ICONE
            c.drawString(x_texto, baseline, _rotulo(pista))
            xc += ICONE + GAP_ICONE + larguras[pista] + GAP

            c.setFillColor(cor_sep)
            c.drawCentredString(xc + w_sep / 2, baseline, separador)
            xc += w_sep + GAP

        c.setFillColor(GRAFITE)
        c.drawString(xc, baseline, texto_total)

    @staticmethod
    def _icone_pista_aquecida(c, cx, cy, size=18):
        """Reproduz o SVG IconePistaAquecida (aquecedor com vapor)."""
        c.saveState()
        c.translate(cx - size / 2, cy - size / 2)
        c.scale(size / 100.0, size / 100.0)

        # Base retangular arredondada (aquecedor)
        c.setFillColor(colors.HexColor("#E65100"))
        c.setStrokeColor(colors.HexColor("#FF9800"))
        c.setLineWidth(2)
        c.roundRect(15, 20, 70, 20, 6, fill=1, stroke=1)

        # Linhas de vapor/fumaça sobre a base
        c.setStrokeColor(colors.HexColor("#FFC107"))
        c.setLineWidth(3)
        c.setLineCap(1)
        for inicio, c1, c2, fim in (
            ((35, 85), (30, 75), (40, 65), (35, 50)),
            ((50, 90), (45, 80), (55, 70), (50, 55)),
            ((65, 85), (60, 75), (70, 65), (65, 50)),
        ):
            caminho = c.beginPath()
            caminho.moveTo(*inicio)
            caminho.curveTo(*c1, *c2, *fim)
            c.drawPath(caminho, stroke=1, fill=0)

        c.restoreState()

    @staticmethod
    def _icone_pista_fria(c, cx, cy, size=18):
        """Reproduz o SVG IconePistaFria (floco de neve central, sem círculo)."""
        c.saveState()
        c.translate(cx - size / 2, cy - size / 2)
        c.scale(size / 24.0, size / 24.0)

        cor = colors.HexColor("#0277BD")
        c.setStrokeColor(cor)

        # Cruz principal
        c.setLineWidth(2)
        c.line(12, 6, 12, 18)
        c.line(6, 12, 18, 12)

        # Diagonais
        c.setLineWidth(1.5)
        c.line(7.75, 7.75, 16.25, 16.25)
        c.line(7.75, 16.25, 16.25, 7.75)

        # Detalhes das ramificações ("V" nas pontas)
        c.setLineWidth(1.5)
        c.line(10, 7, 12, 5)
        c.line(12, 5, 14, 7)
        c.line(10, 17, 12, 19)
        c.line(12, 19, 14, 17)
        c.line(7, 14, 5, 12)
        c.line(5, 12, 7, 10)
        c.line(17, 14, 19, 12)
        c.line(19, 12, 17, 10)

        c.restoreState()
