class LayoutEngine:
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
        """Heurística Bottom-Left dentro de uma zona específica (x_min até x_max)."""
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

                # 2. Tenta rotacionada (se permitido)
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

    def preencher_secao_otimizada(self, catalogo, x_min, x_max, nome_secao):
        """
        Preenche a seção testando combinações verticais (colunas) para maximizar
        o uso da profundidade útil (P), evitando buracos causados por itens gulosos.
        """
        print(f"--- Iniciando preenchimento otimizado: {nome_secao} ---")

        # Agrupa o catálogo por larguras idênticas para formar colunas uniformes
        # Se um item puder rotacionar, criamos uma variante dele com W e H invertidos
        itens_expandidos = []
        for item in catalogo:
            itens_expandidos.append(
                {"nome": item["nome"], "w": item["w"], "h": item["h"]}
            )
            if item.get("rot", False) and item["w"] != item["h"]:
                itens_expandidos.append(
                    {"nome": item["nome"] + " (R)", "w": item["h"], "h": item["w"]}
                )

        larguras_unicas = sorted(list(set([i["w"] for i in itens_expandidos])))

        x_atual = x_min
        while x_atual <= x_max:
            melhor_combinacao = []
            melhor_aproveitamento = -1
            melhor_largura = 0

            # Testamos uma coluna para cada largura disponível no catálogo
            for lw in larguras_unicas:
                if x_atual + lw > x_max:
                    continue

                # Filtra itens que possuem exatamente esta largura de coluna
                itens_da_largura = [i for i in itens_expandidos if i["w"] == lw]
                if not itens_da_largura:
                    continue

                # Encontra recursivamente a melhor combinação vertical para esta largura lw
                comb = self._buscar_melhor_coluna(itens_da_largura, self.P)

                if comb:
                    # Altura total ocupada por essa combinação (somando itens + espaços entre eles)
                    altura_total = (
                        sum(i["h"] for i in comb) + (len(comb) - 1) * self.espaco
                    )

                    # Queremos a combinação que chegue o mais próximo possível de self.P
                    if altura_total > melhor_aproveitamento:
                        melhor_aproveitamento = float(altura_total)
                        melhor_combinacao = comb
                        melhor_largura = lw

            # Se encontramos uma combinação viável para o X atual, nós a alocamos em torre (eixo Y)
            if melhor_combinacao and melhor_largura > 0:
                y_atual = 0.0
                pode_alocar_bloco = True

                # Validação preventiva de segurança para o bloco inteiro
                for item in melhor_combinacao:
                    if not self.cabe(x_atual, y_atual, melhor_largura, item["h"]):
                        pode_alocar_bloco = False
                        break
                    y_atual += item["h"] + self.espaco

                if pode_alocar_bloco:
                    y_atual = 0.0
                    for item in melhor_combinacao:
                        self.itens.append(
                            {
                                "nome": item["nome"],
                                "x": round(x_atual, 2),
                                "y": round(y_atual, 2),
                                "w": melhor_largura,
                                "h": item["h"],
                                "formato": "retangulo",
                            }
                        )
                        y_atual += item["h"] + self.espaco

                    # Avança o X para o fim desta coluna adicionada mais o espaçamento
                    x_atual = round(x_atual + melhor_largura + self.espaco, 2)
                    continue

            # Se nenhuma combinação serviu para este X, avança linearmente para tentar o próximo ponto
            x_atual = round(x_atual + 1.0, 2)

    def _buscar_melhor_coluna(self, itens_disponiveis, altura_maxima):
        """Algoritmo de busca exaustiva para achar o melhor arranjo vertical de itens."""
        melhor_arranjo = []
        maior_altura = -1

        def resolver(arranjo_atual, altura_atual):
            nonlocal melhor_arranjo, maior_altura

            if altura_atual > maior_altura:
                maior_altura = altura_atual
                melhor_arranjo = list(arranjo_atual)

            for item in itens_disponiveis:
                # Se já houver itens, soma o espaçamento necessário entre eles
                custo_espaco = self.espaco if arranjo_atual else 0.0
                nova_altura = altura_atual + custo_espaco + item["h"]

                # Regra estrita: não pode ultrapassar o limite físico da rampa (P)
                if round(nova_altura, 2) <= round(altura_maxima, 2):
                    arranjo_atual.append(item)
                    resolver(arranjo_atual, nova_altura)
                    arranjo_atual.pop()

        resolver([], 0.0)
        return melhor_arranjo
