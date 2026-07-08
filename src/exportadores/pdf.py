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

        topo_atual_y = h_page - 1.0 * cm

        # --- 1. LOGO DA EMPRESA ---
        caminho_logo = os.path.join(PASTA_ASSETS, "logo.png")
        altura_logo = 2.2 * cm
        if os.path.exists(caminho_logo):
            # Desenha a logo centralizada no topo para abrir espaço limpo nas laterais
            c.drawImage(
                caminho_logo,
                (w_page - 6.0 * cm)
                / 2,  # Centraliza a logo horizontalmente (largura estimada de 6cm)
                topo_atual_y - altura_logo,
                height=altura_logo,
                preserveAspectRatio=True,
                mask="auto",
            )
            # Consome o espaço ocupado pela logo + margem de respiro
            topo_atual_y -= altura_logo + 0.5 * cm
        else:
            topo_atual_y -= 0.5 * cm

        # --- 2. INFORMAÇÕES DE CONTATO E ASSINATURA ---
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

        # Linha divisória fina de separação de contexto
        c.setStrokeColor(lightgrey)
        c.setLineWidth(1)
        c.line(1.5 * cm, topo_atual_y, w_page - 1.5 * cm, topo_atual_y)
        topo_atual_y -= 0.6 * cm

        # --- 3. DADOS DO CLIENTE ---
        c.setFont("Helvetica-Bold", 12)
        c.drawString(1.5 * cm, topo_atual_y, f"Cliente: {pedido.nome_cliente}")

        # Recuo de segurança pós-cliente: garante que o bloco do título fique LOGO ABAIXO dele
        topo_atual_y -= 1.2 * cm

        # --- 4. BLOCO CENTRALIZADO HORIZONTALMENTE: OPÇÃO 1 ---
        # Como o ponteiro fluiu livre até aqui, este bloco nunca vai colidir com o cabeçalho superior
        c.setFont("Helvetica-Bold", 24)
        c.drawCentredString(w_page / 2, topo_atual_y, "Opção 1")
        topo_atual_y -= 0.8 * cm

        c.setFont("Helvetica-BoldOblique", 16)
        c.drawCentredString(w_page / 2, topo_atual_y, "Self-Service Quente")
        topo_atual_y -= 0.4 * cm

        # Linha sólida do título centralizado
        c.setStrokeColor(black)
        c.setLineWidth(1.5)
        c.line(w_page / 2 - 5 * cm, topo_atual_y, w_page / 2 + 5 * cm, topo_atual_y)

        # Espaço de folga entre o título e o início do desenho do balcão
        topo_atual_y -= 0.8 * cm

        # --- 5. DESENHO DO BALCÃO E SEUS COMPONENTES ---
        # O offset_y agora aproveita o espaço restante calculado dinamicamente ou fica fixo na base
        offset_y = 2.0 * cm

        for modulo in pedido.modulos:
            largura_real = modulo.engine.L * cm * ESCALA
            altura_real = modulo.engine.P * cm * ESCALA
            offset_x = (w_page - largura_real) / 2

            # --- 5.1. FUNDO DO BALCÃO ---
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

            # --- 5.2. ALOCAÇÃO DAS PANELAS E PEÇAS ---
            for item in modulo.engine.itens:
                w_dim = item["w"] * cm * ESCALA
                h_dim = item["h"] * cm * ESCALA

                x_pos = offset_x + item["x"] * cm * ESCALA
                y_pos = offset_y + altura_real - (item["y"] + item["h"]) * cm * ESCALA

                is_circulo = item.get("formato") == "circulo"

                if is_circulo:
                    w_original = w_dim
                    h_original = h_dim
                    diametro_base = min(w_original, h_original)

                    h_dim = diametro_base * 0.95
                    w_dim = h_dim * 1.08

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

                # Texto do diâmetro/medidas centralizado na peça
                c.setFillColor(black)
                c.setFont("Helvetica-Bold", 8)
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

            # --- 6. RÉGUAS METRICAS (COTAS) ---

            # 6.1. Régua de Largura (Horizontal Inferior)
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
                f"{modulo.engine.L}cm",
            )

            # 6.2. Régua de Profundidade (Vertical Direita)
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
            c.drawCentredString(0, 0, f"{modulo.engine.P}cm")
            c.restoreState()

        c.save()
        print(
            f" > PDF gerado com sucesso com fluxo dinâmico anti-colisão: '{nome_arquivo}'"
        )
