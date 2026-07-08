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
                y_pos = offset_y + altura_real - (item["y"] + item["h"]) * cm * ESCALA

                is_circulo = item.get("formato") == "circulo"

                # AJUSTE VISUAL PARA PANELAS REDONDAS (Evita distorção das alças)
                if is_circulo:
                    w_original = w_dim
                    h_original = h_dim

                    # O diâmetro real (círculo) deve comandar a altura para não achatar
                    # Usamos a menor aresta original como base para o círculo limpo
                    diametro_base = min(w_original, h_original)

                    # Corrigimos a proporção: para o PNG não achatar, a largura com alças
                    # precisa ser ligeiramente maior que a altura (~1.08 vezes maior)
                    h_dim = diametro_base * 0.95
                    w_dim = (
                        h_dim * 1.08
                    )  # Dá o ganho necessário para as alças respirarem nas laterais

                    # Centraliza a imagem corrigida no espaço de colisão original
                    x_pos += (w_original - w_dim) / 2
                    y_pos += (h_original - h_dim) / 2

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
                    y_pos + h_dim / 2 - 3,
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
