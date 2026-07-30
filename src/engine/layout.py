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
        self,
        nome,
        w,
        h,
        x_min,
        x_max,
        formato="retangulo",
        rotacionar=False,
        y_limite_inf=0.0,
    ):
        """Heurística Bottom-Left limpa e sem efeitos colaterais de layout."""
        x_max = min(x_max, self.L)

        passos_x = [x_min]
        for i in self.itens:
            ponto_dir = round(i["x"] + i["w"] + self.espaco, 2)
            if x_min <= ponto_dir <= x_max:
                passos_x.append(ponto_dir)

        passos_y = [y_limite_inf]
        for i in self.itens:
            ponto_sup = round(i["y"] + i["h"] + self.espaco, 2)
            if y_limite_inf <= ponto_sup <= self.P:
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

    def alocar_torre_na_secao(self, torre, x_min, x_max, y_limite_inf=0.0):
        """Alocação puramente sequencial e compacta da torre para posterior distribuição."""
        x_max = min(x_max, self.L)
        w_torre = torre["largura"]

        passos_x = [x_min]
        for i in self.itens:
            ponto_dir = round(i["x"] + i["w"] + self.espaco, 2)
            if x_min <= ponto_dir <= x_max:
                passos_x.append(ponto_dir)

        passos_y = [y_limite_inf]
        for i in self.itens:
            ponto_sup = round(i["y"] + i["h"] + self.espaco, 2)
            if y_limite_inf <= ponto_sup <= self.P:
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
                                "y": py,
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
                    # Aloca os itens de forma linear estável
                    y_linear = py
                    for item_temp in itens_temporarios:
                        item_temp["y"] = y_linear
                        y_linear = round(y_linear + item_temp["h"] + self.espaco, 2)

                    self.itens.extend(itens_temporarios)
                    return True
        return False

    def otimizar_gaps_da_secao(
        self, total_itens_antes, x_min, x_max, y_min=0.0, y_max=None
    ):
        """
        Pós-processador Geométrico Universal (Space-Between bidimensional).
        Distribui de forma homogênea os itens adicionados tanto na horizontal (X) quanto na vertical (Y).
        """
        if y_max is None:
            y_max = self.P

        novos_itens = self.itens[total_itens_antes:]
        if not novos_itens:
            return

        # 1. DISTRIBUIÇÃO HORIZONTAL (EIXO X)
        # Identifica as colunas únicas baseando-se no posicionamento original
        x_originais = sorted(list(set(item["x"] for item in novos_itens)))
        qtd_colunas = len(x_originais)

        if qtd_colunas > 0:
            # Agrupa os itens pertencentes a cada coluna conceitual
            itens_por_coluna = {
                x: [it for it in novos_itens if it["x"] == x] for x in x_originais
            }

            # Descobre a largura real consumida pelas peças de cada coluna (largura da maior peça da coluna)
            larguras_colunas = [
                max(it["w"] for it in itens_por_coluna[x]) for x in x_originais
            ]
            largura_total_itens = sum(larguras_colunas)

            espaco_x_livre = round((x_max - x_min) - largura_total_itens, 2)

            if espaco_x_livre > 0:
                gap_x_uniforme = round(espaco_x_livre / (qtd_colunas + 1), 2)

                # Reaplica as novas coordenadas X deslocando os blocos das colunas
                x_atualizado = round(x_min + gap_x_uniforme, 2)
                for idx, x_orig in enumerate(x_originais):
                    for item in itens_por_coluna[x_orig]:
                        item["x"] = x_atualizado
                    x_atualizado = round(
                        x_atualizado + larguras_colunas[idx] + gap_x_uniforme, 2
                    )

        # 2. DISTRIBUIÇÃO VERTICAL (EIXO Y)
        # Agora analisamos a distribuição vertical de forma estritamente isolada dentro de cada coluna atualizada
        x_novos = set(item["x"] for item in novos_itens)
        for px in x_novos:
            itens_coluna = [it for it in novos_itens if it["x"] == px]
            itens_coluna.sort(key=lambda it: it["y"])
            qtd_itens = len(itens_coluna)

            soma_alturas = sum(it["h"] for it in itens_coluna)
            espaco_y_livre = round((y_max - y_min) - soma_alturas, 2)

            if espaco_y_livre > 0:
                gap_y_uniforme = round(espaco_y_livre / (qtd_itens + 1), 2)

                y_atualizado = round(y_min + gap_y_uniforme, 2)
                for item in itens_coluna:
                    item["y"] = y_atualizado
                    y_atualizado = round(y_atualizado + item["h"] + gap_y_uniforme, 2)

    def preencher_secao_com_torres(
        self,
        torres_prioridade,
        x_min,
        x_max,
        nome_secao,
        y_limite_inf=0.0,
        y_limite_sup=None,
    ):
        """Executa o preenchimento por torre e aciona a otimização de gaps ao final."""
        print(f"--- Iniciando preenchimento com Torres: {nome_secao} ---")
        total_antes = len(self.itens)

        continuar = True
        while continuar:
            adicionou = False
            for torre in torres_prioridade:
                if self.alocar_torre_na_secao(
                    torre, x_min, x_max, y_limite_inf=y_limite_inf
                ):
                    adicionou = True
                    break
            if not adicionou:
                continuar = False

        # Aplica a otimização homogênea em toda a janela delimitada para esta seção
        self.otimizar_gaps_da_secao(
            total_antes, x_min, x_max, y_min=y_limite_inf, y_max=y_limite_sup
        )

    def preencher_secao(
        self,
        catalogo_prioridade,
        x_min,
        x_max,
        nome_secao,
        y_limite_inf=0.0,
        y_limite_sup=None,
    ):
        """Executa o preenchimento guloso padrão e aciona a otimização de gaps ao final."""
        print(f"--- Iniciando preenchimento: {nome_secao} ---")
        total_antes = len(self.itens)

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
                    y_limite_inf=y_limite_inf,
                )
                if sucesso:
                    adicionou = True
                    break
            if not adicionou:
                continuar = False

        # Aplica a otimização homogênea em toda a janela delimitada para esta seção
        self.otimizar_gaps_da_secao(
            total_antes, x_min, x_max, y_min=y_limite_inf, y_max=y_limite_sup
        )
