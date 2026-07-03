import matplotlib.patches as patches
import matplotlib.pyplot as plt


class BonanzaLayoutEngine:
    def __init__(self, comprimento_cm, profundidade_cm, espacamento_cm=0.5):
        self.L = comprimento_cm
        self.P = profundidade_cm
        self.espaco = espacamento_cm
        self.itens = []

    def cabe(self, x, y, w, h):
        """Verifica colisões e limites do balcão, respeitando o espaçamento."""
        if x < 0 or y < 0 or round(x + w, 2) > self.L or round(y + h, 2) > self.P:
            return False

        for i in self.itens:
            ix, iy, iw, ih = i["x"], i["y"], i["w"], i["h"]
            if not (
                round(x + w + self.espaco, 2) <= round(ix, 2)
                or round(x - self.espaco, 2) >= round(ix + iw, 2)
                or round(y + h + self.espaco, 2) <= round(iy, 2)
                or round(y - self.espaco, 2) >= round(iy + ih, 2)
            ):
                return False
        return True

    def obter_limite_direito(self):
        """Retorna a coordenada X máxima ocupada atualmente."""
        if not self.itens:
            return 0.0
        return max(i["x"] + i["w"] for i in self.itens)

    def alocar_na_secao(
        self, nome, w, h, x_min, x_max, formato="retangulo", rotacionar=False
    ):
        """Heurística Bottom-Left dentro de uma zona específica."""
        x_max = min(x_max, self.L)

        passos_x = [x_min] + [
            i["x"] + i["w"] + self.espaco for i in self.itens if i["x"] >= x_min
        ]
        passos_y = [0.0] + [i["y"] + i["h"] + self.espaco for i in self.itens]

        passos_x = sorted(list(set([round(p, 2) for p in passos_x])))
        passos_y = sorted(list(set([round(p, 2) for p in passos_y])))

        for px in passos_x:
            if px + w > x_max and (not rotacionar or px + h > x_max):
                continue

            for py in passos_y:
                # 1. Tenta a orientação original
                if px + w <= x_max and self.cabe(px, py, w, h):
                    self.itens.append(
                        {
                            "nome": nome,
                            "x": px,
                            "y": py,
                            "w": w,
                            "h": h,
                            "formato": formato,
                        }
                    )
                    return True

                # 2. Tenta rotacionada (se permitido pelo catálogo)
                if rotacionar and formato == "retangulo":
                    if px + h <= x_max and self.cabe(px, py, h, w):
                        self.itens.append(
                            {
                                "nome": nome,
                                "x": px,
                                "y": py,
                                "w": h,
                                "h": w,
                                "formato": formato,
                            }
                        )
                        return True
        return False

    def exportar_layout(self, nome_arquivo="layout_secoes_bonanza.pdf"):
        fig, ax = plt.subplots(figsize=(24, (self.P / self.L) * 24))
        ax.set_xlim(0, self.L)
        ax.set_ylim(0, self.P)
        ax.invert_yaxis()
        ax.set_aspect("equal")

        for item in self.itens:
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
                    f"{item['nome']}\n{int(item['w'])}x{int(item['h'])}",
                    ha="center",
                    va="center",
                    color="white",
                    weight="bold",
                    fontsize=8,
                    rotation=rot,
                )

        plt.title(
            f"Layout Técnico Contínuo - {self.L}cm x {self.P}cm | Margem: {self.espaco}cm",
            pad=20,
            fontsize=16,
        )
        plt.xlabel("Comprimento do Balcão (cm)")
        plt.ylabel("Profundidade (cm)")
        plt.grid(True, linestyle=":", alpha=0.4)
        plt.tight_layout()
        plt.savefig(nome_arquivo, format="pdf", dpi=300)
        print(f"Layout gerado e exportado: {nome_arquivo}")

    def preencher_secao(self, catalogo_prioridade, x_min, x_max, nome_secao):
        """Tenta alocar itens iterativamente até não sobrar espaço na zona delimitada."""
        print(f"--- Iniciando preenchimento: {nome_secao} ---")
        continuar = True
        while continuar:
            adicionou = False
            for item in catalogo_prioridade:
                sucesso = self.alocar_na_secao(
                    item["nome"],
                    w=item["w"],
                    h=item["h"],
                    x_min=x_min,
                    x_max=x_max,
                    formato="retangulo",
                    rotacionar=item.get("rot", False),
                )
                if sucesso:
                    adicionou = True
                    break
            if not adicionou:
                continuar = False


# ==========================================
# CONFIGURAÇÃO DE SEÇÕES
# ==========================================
PCT_FIM_SECOES_1_2_3 = 0.75

# ==========================================
# EXECUÇÃO DO MOTOR
# ==========================================
balcao = BonanzaLayoutEngine(comprimento_cm=200, profundidade_cm=50, espacamento_cm=0.5)

# --- 1. SEÇÃO 1: PAREDE DE PANELAS REDONDAS ---
qtd_panelas_redondas_desejada = 2
diametros_permitidos = [34, 32, 30, 28, 26, 24, 22]
alocadas_redondas = 0

print("--- Iniciando alocação: Seção 1 (Redondas) ---")
for i in range(qtd_panelas_redondas_desejada):
    alocado = False
    nome = "Arroz" if alocadas_redondas % 2 == 0 else "Feijão"

    for d in diametros_permitidos:
        # A Seção 1 é limitada a bater no máximo no limite onde a Seção 4 deve começar
        limite_s1_maximo = balcao.L * PCT_FIM_SECOES_1_2_3
        if balcao.alocar_na_secao(
            nome, w=d, h=d, x_min=0, x_max=limite_s1_maximo, formato="circulo"
        ):
            alocadas_redondas += 1
            alocado = True
            break  # Passa para a próxima panela

    if not alocado:
        # Se não coube nem a de 22cm, o limite de espaço físico ou de seção estourou
        break

# Output de verificação das Redondas
print("\nStatus Panelas Redondas:")
if alocadas_redondas < qtd_panelas_redondas_desejada:
    print(
        f"⚠ ATENÇÃO: Espaço insuficiente. Foram preenchidas {alocadas_redondas}/{qtd_panelas_redondas_desejada} panelas."
    )
else:
    print(
        f"✅ Sucesso: Todas as {qtd_panelas_redondas_desejada}/{qtd_panelas_redondas_desejada} panelas redondas foram alocadas."
    )
print("-" * 40)

# --- 2. PREENCHIMENTO DOS GAPS DA SEÇÃO 1 ---
# Trava o limite da Seção 1 exatamente na borda direita da última panela redonda alocada.
# Isso garante que as travessas de tapa-buraco não "empurrem" o resto do balcão para frente.
limite_fisico_s1 = balcao.obter_limite_direito()

cat_tapa_buracos_s1 = [
    {"nome": "Tapa 21x44", "w": 21, "h": 44, "rot": True},
    {"nome": "Tapa 21x32", "w": 21, "h": 32, "rot": True},
    {"nome": "Tapa 21x21", "w": 21, "h": 21, "rot": True},
    {"nome": "Tapa 21x13", "w": 21, "h": 13, "rot": True},
]
balcao.preencher_secao(
    cat_tapa_buracos_s1, 0, limite_fisico_s1, "Preenchimento Gaps Seção 1"
)

# --- 3. SEÇÕES 2 E 3 (Grandes Verticais) ---
x_start_s2 = limite_fisico_s1 + balcao.espaco
limite_secoes_2_3 = round(balcao.L * PCT_FIM_SECOES_1_2_3, 2)

cat_s2_s3 = [
    {"nome": "Quente G", "w": 21, "h": 53},
    {"nome": "Quente M", "w": 21, "h": 21},
    {"nome": "Quente P", "w": 21, "h": 13},
]
balcao.preencher_secao(cat_s2_s3, x_start_s2, limite_secoes_2_3, "Seções 2+3")

# --- 4. SEÇÃO 4 (Finais) ---
x_start_s4 = balcao.obter_limite_direito() + balcao.espaco
cat_s4 = [
    {"nome": "Salada Prin.", "w": 21, "h": 32},
    {"nome": "Fina", "w": 13, "h": 32, "rot": True},
    {"nome": "Guarnição M", "w": 21, "h": 21},
    {"nome": "Guarnição P", "w": 21, "h": 13, "rot": True},
]
balcao.preencher_secao(cat_s4, x_start_s4, balcao.L, "Seção 4")

# Exportar
balcao.exportar_layout()
