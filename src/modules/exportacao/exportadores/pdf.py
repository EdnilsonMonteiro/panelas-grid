import os
from pathlib import Path

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


class ExportadorPDF:
    @staticmethod
    def gerar_layout(pedido, nome_arquivo):
        ESCALA = 0.1  # Escala 1:10

        # --- 1. CÁLCULO DA LARGURA DINÂMICA DA PÁGINA ---
        # Encontra o maior comprimento (L) entre os módulos do pedido
        maior_comprimento_balcao_cm = max(modulo.engine.L for modulo in pedido.modulos)
        largura_balcao_no_pdf = maior_comprimento_balcao_cm * cm * ESCALA

        # Define uma folga de segurança de 20cm reais no PDF (10cm de cada lado para as cotas e respiro)
        largura_calculada_pdf = largura_balcao_no_pdf + (20.0 * cm)

        # Resgata as dimensões padrão do A4 em modo paisagem para referência mínima
        w_a4_landscape, h_a4_landscape = landscape(A4)

        # Garante que a página tenha no mínimo o tamanho de um A4 de largura
        w_page = max(largura_calculada_pdf, w_a4_landscape)
        h_page = h_a4_landscape  # Mantém a altura padrão estável

        # Inicializa o canvas com o tamanho de página dinâmico
        c = canvas.Canvas(nome_arquivo, pagesize=(w_page, h_page))

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

        # --- 5. BLOCO CENTRALIZADO DINAMICAMENTE: OPÇÃO 1 ---
        c.setFont("Helvetica-Bold", 24)
        c.drawCentredString(w_page / 2, topo_atual_y, "Opção 1")
        topo_atual_y -= 0.8 * cm

        c.setFont("Helvetica-BoldOblique", 16)
        c.drawCentredString(w_page / 2, topo_atual_y, "Self-Service Quente")
        topo_atual_y -= 0.4 * cm

        # Linha sólida do título centralizada na nova página
        c.setStrokeColor(black)
        c.setLineWidth(1.5)
        c.line(w_page / 2 - 5 * cm, topo_atual_y, w_page / 2 + 5 * cm, topo_atual_y)
        topo_atual_y -= 0.8 * cm

        # --- 6. DESENHO DO BALCÃO E SEUS COMPONENTES ---
        offset_y = 2.0 * cm

        for modulo in pedido.modulos:
            largura_real = modulo.engine.L * cm * ESCALA
            altura_real = modulo.engine.P * cm * ESCALA

            # Recalcula o offset_x dinamicamente para o centro da nova página expandida
            offset_x = (w_page - largura_real) / 2

            # --- 6.1. FUNDO DO BALCÃO ---
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

            # --- 6.2. ALOCAÇÃO DAS PANELAS E PEÇAS ---
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

            # --- 7. RÉGUAS MÉTRICAS (COTAS) ---

            # 7.1. Régua de Largura (Horizontal Inferior)
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

            # 7.2. Régua de Profundidade (Vertical Direita)
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
        print(f" > PDF gerado com sucesso com dimensões adaptativas: '{nome_arquivo}'")
