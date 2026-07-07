import os

from reportlab.lib.colors import black, lightgrey, white
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas

DIRETORIO_EXPORTADOR = os.path.dirname(os.path.abspath(__file__))
PASTA_SRC = os.path.abspath(os.path.join(DIRETORIO_EXPORTADOR, ".."))

PASTA_RAIZ_PROJETO = os.path.abspath(os.path.join(PASTA_SRC, ".."))

PASTA_ASSETS = os.path.join(PASTA_RAIZ_PROJETO, "assets")

print(f" > Buscando assets em: {PASTA_ASSETS}")


class ExportadorPDF:
    @staticmethod
    def gerar_layout(pedido, nome_arquivo):
        c = canvas.Canvas(nome_arquivo, pagesize=landscape(A4))
        w_page, h_page = landscape(A4)
        ESCALA = 0.1  # Escala 1:10

        # --- 1. CABEÇALHO ---
        caminho_logo = os.path.join(PASTA_ASSETS, "logo.png")
        if os.path.exists(caminho_logo):
            c.drawImage(
                caminho_logo,
                1 * cm,
                h_page - 3.5 * cm,
                height=2.5 * cm,
                preserveAspectRatio=True,
                mask="auto",
            )

        c.setFont("Helvetica-Bold", 11)
        c.drawString(
            1 * cm,
            h_page - 4.0 * cm,
            "Linha Definitiva Solução em Travessas para Self-Service",
        )
        c.setFont("Helvetica", 11)
        c.drawString(
            1 * cm, h_page - 4.5 * cm, "@Bonanza_Travessasebalcoes 31-99084-4400"
        )
        c.setStrokeColor(black)
        c.setLineWidth(1.5)
        c.line(1 * cm, h_page - 4.7 * cm, 12.5 * cm, h_page - 4.7 * cm)

        c.setFont("Helvetica-Bold", 12)
        c.drawString(1 * cm, h_page - 5.5 * cm, f"Cliente: {pedido.nome_cliente}")

        c.setFont("Helvetica-Bold", 20)
        c.drawCentredString(w_page / 2 + 5 * cm, h_page - 2.5 * cm, "Opção 1")
        c.setFont("Helvetica-BoldOblique", 18)
        c.drawCentredString(
            w_page / 2 + 5 * cm, h_page - 3.2 * cm, "Self-Service Quente"
        )
        c.setStrokeColor(black)
        c.setLineWidth(1.5)
        c.line(w_page / 2, h_page - 3.4 * cm, w_page / 2 + 10 * cm, h_page - 3.4 * cm)

        # --- 2. DESENHO DOS MÓDULOS ---
        offset_y = 9.5 * cm

        for modulo in pedido.modulos:
            largura_real = modulo.engine.L * cm * ESCALA
            altura_real = modulo.engine.P * cm * ESCALA
            offset_x = (w_page - largura_real) / 2

            # --- 3. FUNDO DO BALCÃO ---
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

            # --- 4. ALOCAÇÃO DAS PANELAS ---
            for item in modulo.engine.itens:
                w_dim = item["w"] * cm * ESCALA
                h_dim = item["h"] * cm * ESCALA

                x_pos = offset_x + item["x"] * cm * ESCALA

                # ─────────────────────────────────────────────────────────────
                # CORREÇÃO DO EIXO Y
                # O motor de layout usa y=0 no TOPO (eixo cresce para baixo).
                # O ReportLab usa y=0 na BASE (eixo cresce para cima).
                # Fórmula: y_RL = offset_y + altura_total - (y_motor + h_item)
                # ─────────────────────────────────────────────────────────────
                y_pos = offset_y + altura_real - (item["y"] + item["h"]) * cm * ESCALA

                is_circulo = item.get("formato") == "circulo"
                caminho_panela_redonda = os.path.join(
                    PASTA_ASSETS, "panela_redonda.png"
                )
                caminho_panela_retangular = os.path.join(
                    PASTA_ASSETS, "panela_retangular.png"
                )
                img_path = (
                    caminho_panela_redonda if is_circulo else caminho_panela_retangular
                )

                if os.path.exists(img_path):
                    c.drawImage(img_path, x_pos, y_pos, w_dim, h_dim, mask="auto")
                else:
                    c.setFillColor(white)
                    c.setStrokeColor(black)
                    if is_circulo:
                        # ellipse(x1, y1, x2, y2): canto inferior-esquerdo e superior-direito
                        c.ellipse(
                            x_pos, y_pos, x_pos + w_dim, y_pos + h_dim, fill=1, stroke=1
                        )
                    else:
                        c.rect(x_pos, y_pos, w_dim, h_dim, fill=1, stroke=1)

                # Texto centralizado na panela
                c.setFillColor(black)
                c.setFont("Helvetica-Bold", 8)
                texto_panela = (
                    f"{int(item['w'])}"
                    if is_circulo
                    else f"{int(item['w'])}x{int(item['h'])}"
                )
                # y_pos é o fundo da panela em coords RL → centro = y_pos + h_dim/2
                c.drawCentredString(
                    x_pos + w_dim / 2,
                    y_pos
                    + h_dim / 2
                    - 3,  # -3pt para centralizar visualmente a baseline
                    texto_panela,
                )

            # --- 5. MARCADORES DE DIMENSÃO ---

            # 5.1. Chave inferior (Largura)
            chave_y = offset_y - 1.2 * cm
            c.setStrokeColor(black)
            c.setLineWidth(1.5)
            c.line(offset_x, chave_y, offset_x + largura_real, chave_y)
            c.line(offset_x, chave_y - 0.3 * cm, offset_x, chave_y + 0.3 * cm)
            c.line(
                offset_x + largura_real,
                chave_y - 0.3 * cm,
                offset_x + largura_real,
                chave_y + 0.3 * cm,
            )
            c.setFont("Helvetica-Bold", 16)
            c.drawCentredString(
                offset_x + largura_real / 2,
                chave_y - 0.8 * cm,
                f"{modulo.engine.L}cm",
            )

            # 5.2. Chave lateral direita (Profundidade)
            chave_x = offset_x + largura_real + 0.5 * cm
            c.setStrokeColor(black)
            c.setLineWidth(1.5)
            c.line(chave_x, offset_y, chave_x, offset_y + altura_real)
            c.line(
                chave_x - 0.3 * cm,
                offset_y + altura_real,
                chave_x + 0.3 * cm,
                offset_y + altura_real,
            )
            c.line(chave_x - 0.3 * cm, offset_y, chave_x + 0.3 * cm, offset_y)
            c.saveState()
            c.translate(chave_x + 0.8 * cm, offset_y + altura_real / 2)
            c.rotate(90)
            c.setFont("Helvetica-Bold", 16)
            c.drawCentredString(0, 0, f"{modulo.engine.P}cm")
            c.restoreState()

        c.save()
        print(f" > PDF gerado com sucesso: '{nome_arquivo}'")
