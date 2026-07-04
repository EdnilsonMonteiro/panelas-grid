import matplotlib.patches as patches
import matplotlib.pyplot as plt


class ExportadorPDF:
    @staticmethod
    def gerar_layout(pedido_cliente, nome_arquivo="layout_final.pdf"):
        num_modulos = len(pedido_cliente.modulos)
        if num_modulos == 0:
            print("Nenhum módulo para exportar.")
            return

        # Cria uma linha de subplots, um para cada placa/módulo do balcão
        fig, axes = plt.subplots(
            num_modulos, 1, figsize=(24, 8 * num_modulos), squeeze=False
        )

        for idx, modulo in enumerate(pedido_cliente.modulos):
            ax = axes[idx, 0]
            ax.set_xlim(0, modulo.L)
            ax.set_ylim(0, modulo.P)
            ax.invert_yaxis()
            ax.set_aspect("equal")

            for item in modulo.itens:
                x, y, w, h = item["x"], item["y"], item["w"], item["h"]

                if item["formato"] == "circulo":
                    cor = "#D84315" if "Feijão" in item["nome"] else "#FFB300"
                    raio = w / 2
                    cx, cy = x + raio, y + raio
                    circ = patches.Circle(
                        (cx, cy),
                        raio,
                        linewidth=2,
                        edgecolor="#ffffff",
                        facecolor=cor,
                        alpha=0.9,
                    )
                    ax.add_patch(circ)
                    ax.text(
                        cx,
                        cy,
                        f"{item['nome']}\nØ{int(w)}",
                        ha="center",
                        va="center",
                        color="white",
                        weight="bold",
                        fontsize=9,
                    )
                else:
                    cor = (
                        "#1565C0"
                        if h >= 53 or w >= 53
                        else ("#2E7D32" if h >= 32 or w >= 32 else "#6A1B9A")
                    )
                    rect = patches.Rectangle(
                        (x, y),
                        w,
                        h,
                        linewidth=1.5,
                        edgecolor="#ffffff",
                        facecolor=cor,
                        alpha=0.85,
                    )
                    ax.add_patch(rect)
                    cx, cy = x + w / 2, y + h / 2
                    rot = 90 if w < h and w <= 21 else 0
                    ax.text(
                        cx,
                        cy,
                        f"{item['nome']}\n{int(w)}x{int(h)}",
                        ha="center",
                        va="center",
                        color="white",
                        weight="bold",
                        fontsize=8,
                        rotation=rot,
                    )

            ax.set_title(
                f"Módulo {idx + 1}: {modulo.tipo_rampa.upper()} - {modulo.L}cm x {modulo.P}cm",
                fontsize=14,
                pad=10,
            )
            ax.set_xlabel("Comprimento (cm)")
            ax.set_ylabel("Profundidade (cm)")
            ax.grid(True, linestyle=":", alpha=0.4)

        plt.suptitle(
            f"Layout Técnico - Cliente: {pedido_cliente.nome_cliente}",
            fontsize=18,
            weight="bold",
            y=0.98,
        )
        plt.tight_layout()
        plt.savefig(nome_arquivo, format="pdf", dpi=300)
        plt.close()
        print(f"Layout multimodular exportado com sucesso: {nome_arquivo}")
