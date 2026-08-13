import os
from pathlib import Path
from typing import List

from reportlab.lib.colors import black, lightgrey, white
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas

ARQUIVO_ATUAL = Path(__file__).resolve()

PASTA_RAIZ_PROJETO = next(
    p for p in ARQUIVO_ATUAL.parents if (p / "assets").exists() or (p / "src").exists()
)

PASTA_ASSETS = PASTA_RAIZ_PROJETO / "assets"

print(f" > Buscando assets em: {PASTA_ASSETS}")

TITULO_PADRAO = "Self-Service Quente"

GAP_PLACAS = 1.0  # cm de espaçamento entre placas (multiplacas)


class ExportadorPDF:
    @staticmethod
    def gerar_layout(pedido, nome_arquivo):
        """Gera o PDF de um único layout (backward compatibility)."""
        ExportadorPDF.gerar_layouts([pedido], [TITULO_PADRAO], nome_arquivo)

    @staticmethod
    def gerar_layouts(pedidos: List, nomes_opcoes: List[str], nome_arquivo: str):
        """Gera o PDF com uma página por pedido (uma 'Opção' por página).

        `pedidos` é a lista de ComposicaoBalcao calculadas e `nomes_opcoes`
        contém o título (subtítulo) de cada opção, na mesma ordem.
        """
        ESCALA = 0.1  # Escala 1:10

        # --- 1. CÁLCULO DA LARGURA DINÂMICA DA PÁGINA ---
        # Largura total do grupo de placas de cada pedido (soma das larguras + gaps)
        def _largura_total_pedido(pedido):
            larguras = [modulo.engine.L for modulo in pedido.modulos]
            return sum(larguras) + GAP_PLACAS * (len(larguras) - 1)

        maior_largura_cm = max(_largura_total_pedido(p) for p in pedidos)
        largura_balcao_no_pdf = maior_largura_cm * cm * ESCALA

        # Define uma folga de segurança de 20cm reais no PDF (10cm de cada lado para as cotas e respiro)
        largura_calculada_pdf = largura_balcao_no_pdf + (20.0 * cm)

        # Resgata as dimensões padrão do A4 em modo paisagem para referência mínima
        w_a4_landscape, h_a4_landscape = landscape(A4)

        # Garante que a página tenha no mínimo o tamanho de um A4 de largura
        w_page = max(largura_calculada_pdf, w_a4_landscape)
        h_page = h_a4_landscape  # Mantém a altura padrão estável

        # Inicializa o canvas com o tamanho de página dinâmico
        c = canvas.Canvas(nome_arquivo, pagesize=(w_page, h_page))

        for indice, pedido in enumerate(pedidos):
            titulo = (
                nomes_opcoes[indice] if indice < len(nomes_opcoes) else TITULO_PADRAO
            )
            ExportadorPDF._desenhar_pagina(c, pedido, indice + 1, titulo, w_page, h_page)
            if indice < len(pedidos) - 1:
                c.showPage()

        c.save()
        print(f" > PDF gerado com sucesso com dimensões adaptativas: '{nome_arquivo}'")

    @staticmethod
    def _desenhar_balcao(
        c, modulo, offset_x, offset_y, escala, exibir_texto=True, tamanho_texto=8
    ):
        """Desenha o balcão (fundo) e as panelas/peças alocadas em um módulo.

        Reutilizável: a página completa usa `escala=0.1`; miniaturas usam uma
        escala calculada para caberem na caixa desejada. O texto de medida só
        é desenhado quando a peça é grande o suficiente para lê-lo.
        """
        largura_real = modulo.engine.L * cm * escala
        altura_real = modulo.engine.P * cm * escala

        # --- FUNDO DO BALCÃO ---
        caminho_fundo = os.path.join(PASTA_ASSETS, "fundo_perfurado.png")
        if os.path.exists(caminho_fundo):
            c.drawImage(
                caminho_fundo,
                offset_x,
                offset_y,
                largura_real,
                altura_real,
                mask="auto",
            )
        else:
            c.setFillColor(lightgrey)
            c.setStrokeColor(black)
            c.rect(offset_x, offset_y, largura_real, altura_real, fill=1, stroke=1)

        # --- ALOCAÇÃO DAS PANELAS E PEÇAS ---
        caminho_panela_redonda = os.path.join(PASTA_ASSETS, "panela_redonda.png")
        caminho_panela_retangular = os.path.join(
            PASTA_ASSETS, "panela_retangular.png"
        )

        for item in modulo.engine.itens:
            w_dim = item["w"] * cm * escala
            h_dim = item["h"] * cm * escala

            x_pos = offset_x + item["x"] * cm * escala
            y_pos = offset_y + altura_real - (item["y"] + item["h"]) * cm * escala

            is_circulo = item.get("formato") == "circulo"

            if is_circulo:
                w_original = w_dim
                h_original = h_dim
                diametro_base = min(w_original, h_original)

                h_dim = diametro_base * 0.95
                w_dim = h_dim * 1.08

                x_pos += (w_original - w_dim) / 2
                y_pos += (h_original - h_dim) / 2

            img_path = (
                caminho_panela_redonda if is_circulo else caminho_panela_retangular
            )

            if os.path.exists(img_path):
                if is_circulo:
                    c.saveState()
                    c.translate(x_pos + w_dim / 2, y_pos + h_dim / 2)
                    c.rotate(33.8)
                    c.drawImage(
                        img_path, -w_dim / 2, -h_dim / 2, w_dim, h_dim, mask="auto"
                    )
                    c.restoreState()
                else:
                    c.drawImage(img_path, x_pos, y_pos, w_dim, h_dim, mask="auto")
            else:
                c.setFillColor(white)
                c.setStrokeColor(black)
                if is_circulo:
                    c.ellipse(
                        x_pos, y_pos, x_pos + w_dim, y_pos + h_dim, fill=1, stroke=1
                    )
                else:
                    c.rect(x_pos, y_pos, w_dim, h_dim, fill=1, stroke=1)

            if exibir_texto and min(w_dim, h_dim) >= 12:
                # Texto do diâmetro/medidas centralizado na peça
                c.setFillColor(black)
                c.setFont("Helvetica-Bold", tamanho_texto)
                texto_panela = (
                    f"{int(item['w'])}"
                    if is_circulo
                    else f"{int(item['w'])}x{int(item['h'])}"
                )
                c.drawCentredString(
                    x_pos + w_dim / 2,
                    y_pos + h_dim / 2 - 3,
                    texto_panela,
                )

    @staticmethod
    def _desenhar_pagina(c, pedido, num_opcao, titulo, w_page, h_page):
        """Desenha o conteúdo de uma única página (uma opção) do PDF."""
        ESCALA = 0.1

        topo_atual_y = h_page - 1.0 * cm

        # --- 2. LOGO DA EMPRESA ---
        caminho_logo = os.path.join(PASTA_ASSETS, "logo.png")
        altura_logo = 2.2 * cm
        if os.path.exists(caminho_logo):
            # Desenha a logo centralizada no topo baseado na nova largura dinâmica
            c.drawImage(
                caminho_logo,
                (w_page - 6.0 * cm) / 2,  # Centraliza usando a nova largura total
                topo_atual_y - altura_logo,
                height=altura_logo,
                preserveAspectRatio=True,
                mask="auto",
            )
            topo_atual_y -= altura_logo + 0.5 * cm
        else:
            topo_atual_y -= 0.5 * cm

        # --- 3. INFORMAÇÕES DE CONTATO E ASSINATURA ---
        c.setFont("Helvetica-Bold", 10)
        c.drawString(
            1.5 * cm,
            topo_atual_y,
            "Linha Definitiva Solução em Travessas para Self-Service",
        )
        topo_atual_y -= 0.5 * cm

        c.setFont("Helvetica", 10)
        c.setFillColor(black)
        c.drawString(
            1.5 * cm, topo_atual_y, "@Bonanza_Travessasebalcoes  |  31-99084-4400"
        )
        topo_atual_y -= 0.3 * cm

        # Linha divisória estendendo-se por toda a nova largura da página (com margem de 1.5cm)
        c.setStrokeColor(lightgrey)
        c.setLineWidth(1)
        c.line(1.5 * cm, topo_atual_y, w_page - 1.5 * cm, topo_atual_y)
        topo_atual_y -= 0.6 * cm

        # --- 4. DADOS DO CLIENTE ---
        c.setFont("Helvetica-Bold", 12)
        c.drawString(1.5 * cm, topo_atual_y, f"Cliente: {pedido.nome_cliente}")
        topo_atual_y -= 1.2 * cm

        # --- 5. BLOCO CENTRALIZADO DINAMICAMENTE: OPÇÃO N ---
        c.setFont("Helvetica-Bold", 24)
        c.drawCentredString(w_page / 2, topo_atual_y, f"Opção {num_opcao}")
        topo_atual_y -= 0.8 * cm

        c.setFont("Helvetica-BoldOblique", 16)
        c.drawCentredString(w_page / 2, topo_atual_y, titulo)
        topo_atual_y -= 0.4 * cm

        # Linha sólida do título centralizada na nova página
        c.setStrokeColor(black)
        c.setLineWidth(1.5)
        c.line(w_page / 2 - 5 * cm, topo_atual_y, w_page / 2 + 5 * cm, topo_atual_y)
        topo_atual_y -= 0.8 * cm

        # --- 6. DESENHO DO BALCÃO E SEUS COMPONENTES (placas lado a lado) ---
        offset_y = 2.0 * cm

        modulos = pedido.modulos
        larguras_reais = [m.engine.L * cm * ESCALA for m in modulos]
        alturas_reais = [m.engine.P * cm * ESCALA for m in modulos]
        gap_real = GAP_PLACAS * cm * ESCALA
        largura_grupo = sum(larguras_reais) + gap_real * (len(modulos) - 1)
        x_atual = (w_page - largura_grupo) / 2

        for indice, modulo in enumerate(modulos):
            largura_real = larguras_reais[indice]
            altura_real = alturas_reais[indice]
            offset_x = x_atual

            ExportadorPDF._desenhar_balcao(
                c, modulo, offset_x, offset_y, ESCALA, exibir_texto=True
            )

            # --- 7. RÉGUAS MÉTRICAS (COTAS) ---

            # 7.1. Régua de Largura (Horizontal Inferior) — abaixo de cada placa
            chave_y = offset_y - 1.0 * cm
            c.setStrokeColor(black)
            c.setLineWidth(1.5)
            c.line(offset_x, chave_y, offset_x + largura_real, chave_y)
            c.line(offset_x, chave_y - 0.2 * cm, offset_x, chave_y + 0.2 * cm)
            c.line(
                offset_x + largura_real,
                chave_y - 0.2 * cm,
                offset_x + largura_real,
                chave_y + 0.2 * cm,
            )
            c.setFont("Helvetica-Bold", 14)
            c.drawCentredString(
                offset_x + largura_real / 2,
                chave_y - 0.6 * cm,
                f"{modulo.engine.L:g}cm",
            )

            # 7.2. Régua de Profundidade (Vertical Direita) — altura única no fim
            if indice == len(modulos) - 1:
                chave_x = offset_x + largura_real + 0.5 * cm
                c.setStrokeColor(black)
                c.setLineWidth(1.5)
                c.line(chave_x, offset_y, chave_x, offset_y + altura_real)
                c.line(
                    chave_x - 0.2 * cm,
                    offset_y + altura_real,
                    chave_x + 0.2 * cm,
                    offset_y + altura_real,
                )
                c.line(chave_x - 0.2 * cm, offset_y, chave_x + 0.2 * cm, offset_y)

                c.saveState()
                c.translate(chave_x + 0.6 * cm, offset_y + altura_real / 2)
                c.rotate(90)
                c.setFont("Helvetica-Bold", 14)
                c.drawCentredString(0, 0, f"{modulo.engine.P:g}cm")
                c.restoreState()

            x_atual += largura_real + gap_real
