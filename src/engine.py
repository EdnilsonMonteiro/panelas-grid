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
        """Heurística Bottom-Left dentro de uma zona específica com tratamento de espaçamento corrigido."""
        x_max = min(x_max, self.L)

        passos_x = [x_min]
        for i in self.itens:
            ponto_dir = round(i["x"] + i["w"] + self.espaco, 2)
            if x_min <= ponto_dir <= x_max:
                passos_x.append(ponto_dir)

        passos_y = [0.0]
        for i in self.itens:
            ponto_sup = round(i["y"] + i["h"] + self.espaco, 2)
            if ponto_sup <= self.P:
                passos_y.append(ponto_sup)

        passos_x = sorted(list(set(passos_x)))
        passos_y = sorted(list(set(passos_y)))

        for px in passos_x:
            if px + w > x_max and (not rotacionar or px + h > x_max):
                continue

            for py in passos_y:
                if round(px + w, 2) <= x_max and self.cabe(px, py, w, h):
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

                if rotacionar and formato == "retangulo":
                    if round(px + h, 2) <= x_max and self.cabe(px, py, h, w):
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

    def alocar_torre_na_secao(self, torre, x_min, x_max):
        """Tenta alocar uma estrutura de torre vertical completa respeitando espaçamentos de seções adjacentes."""
        x_max = min(x_max, self.L)
        w_torre = torre["largura"]

        passos_x = [x_min]
        for i in self.itens:
            ponto_dir = round(i["x"] + i["w"] + self.espaco, 2)
            if x_min <= ponto_dir <= x_max:
                passos_x.append(ponto_dir)

        passos_y = [0.0]
        for i in self.itens:
            ponto_sup = round(i["y"] + i["h"] + self.espaco, 2)
            if ponto_sup <= self.P:
                passos_y.append(ponto_sup)

        passos_x = sorted(list(set(passos_x)))
        passos_y = sorted(list(set(passos_y)))

        for px in passos_x:
            if px + w_torre > x_max:
                continue

            for py in passos_y:
                y_atual = py
                torre_cabe = True
                itens_temporarios = []

                for item in torre["itens"]:
                    if self.cabe(px, y_atual, w_torre, item["h"]):
                        itens_temporarios.append(
                            {
                                "nome": item["nome"],
                                "x": px,
                                "y": y_atual,
                                "w": w_torre,
                                "h": item["h"],
                                "formato": "retangulo",
                            }
                        )
                        y_atual = round(y_atual + item["h"] + self.espaco, 2)
                    else:
                        torre_cabe = False
                        break

                if torre_cabe:
                    print(f"Torre acoplada com sucesso em X:{px} Y:{py}!")
                    self.itens.extend(itens_temporarios)
                    return True
        return False

    def preencher_secao_com_torres(self, torres_prioridade, x_min, x_max, nome_secao):
        """Preenche a seção testando as melhores configurações de torres verticais inteiras."""
        print(f"--- Iniciando preenchimento com Torres: {nome_secao} ---")
        continuar = True
        while continuar:
            adicionou = False
            for torre in torres_prioridade:
                if self.alocar_torre_na_secao(torre, x_min, x_max):
                    adicionou = True
                    break
            if not adicionou:
                continuar = False

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
