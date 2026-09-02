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

    def alocar_sequencia_fixa(
        self,
        itens_ordenados,
        x_min,
        x_max,
        nome_secao,
        y_limite_inf=0.0,
    ):
        """Preenche a seção repetindo verticalmente o padrão de coluna.

        As travessas são empilhadas DE CIMA para BAIXO (a primeira da ordem
        fica no topo), formando uma coluna única que é repetida
        horizontalmente enquanto houver largura disponível na janela da
        seção. Ao final aplica a mesma distribuição homogênea de gaps das
        demais seções, preservando a ordem escolhida.

        Se o padrão não couber — altura da coluna maior que a profundidade
        do balcão ou travessa mais larga que a janela — nada é alocado e um
        ValueError explicativo é lançado (a UI exibe a mensagem).
        """
        print(
            f"--- Iniciando preenchimento com ordem fixa (colunas): {nome_secao} ---"
        )

        def fmt(valor):
            return f"{float(valor):g}"

        erros = []
        travessas = []

        for indice, item in enumerate(itens_ordenados, start=1):
            if not isinstance(item, dict) or not item.get("nome"):
                erros.append(
                    f"A seção '{nome_secao}' tem um item inválido na posição"
                    f" {indice} da ordem de preenchimento."
                )
                continue

            nome = str(item["nome"])
            rotacionar = bool(item.get("rot", False))
            try:
                w_original = float(item.get("w") or 0.0)
                h_original = float(item.get("h") or 0.0)
            except (TypeError, ValueError):
                w_original = h_original = 0.0

            if w_original <= 0 or h_original <= 0:
                erros.append(
                    f"A travessa '{nome}' (posição {indice}) está sem"
                    f" dimensões válidas."
                )
                continue

            # A rotação troca largura x altura (mesma regra do motor guloso)
            w_efetivo, h_efetivo = (
                (h_original, w_original)
                if rotacionar
                else (w_original, h_original)
            )

            travessas.append({"nome": nome, "w": w_efetivo, "h": h_efetivo})

        if not travessas:
            if erros:
                raise ValueError(
                    "Não foi possível montar o preenchimento fixo. "
                    + " ".join(erros)
                )
            raise ValueError(
                f"A seção '{nome_secao}' não tem travessas válidas na ordem"
                f" de preenchimento."
            )

        # Altura do padrão de coluna (empilhado de cima para baixo)
        altura_coluna = round(
            sum(t["h"] for t in travessas)
            + self.espaco * (len(travessas) - 1),
            2,
        )
        if round(y_limite_inf + altura_coluna, 2) > round(self.P, 2):
            erros.append(
                f"O padrão de coluna da seção '{nome_secao}' soma"
                f" {fmt(altura_coluna)} cm de altura (incluindo o"
                f" espaçamento de {fmt(self.espaco)} cm entre as travessas),"
                f" mas a profundidade do balcão é de apenas {fmt(self.P)} cm."
                f" Remova travessas da sequência ou rotacione as mais altas."
            )

        # Largura: a coluna tem a largura da travessa mais larga do padrão
        largura_coluna = round(max(t["w"] for t in travessas), 2)
        largura_disponivel = round(min(x_max, self.L) - x_min, 2)
        if largura_coluna > largura_disponivel:
            erros.append(
                f"A travessa mais larga do padrão da seção '{nome_secao}'"
                f" tem {fmt(largura_coluna)} cm de largura, mas a largura"
                f" disponível para esta seção no balcão é de apenas"
                f" {fmt(largura_disponivel)} cm (balcão com {fmt(self.L)} cm"
                f" de comprimento). Rotacione travessas, troque por travessas"
                f" mais estreitas ou aumente o '% do Espaço Restante' da"
                f" seção."
            )
        qtd_colunas = max(
            1,
            int(
                (largura_disponivel + self.espaco)
                // (largura_coluna + self.espaco)
            ),
        )

        if erros:
            raise ValueError(
                "Não foi possível montar o preenchimento fixo. "
                + " ".join(erros)
            )

        # Monta as colunas repetindo o padrão. O eixo Y do motor é desenhado
        # invertido (y=0 é o topo visual no PDF/PPTX), então a primeira
        # travessa da ordem fica em y_limite_inf — o TOPO visual — e as
        # seguintes empilham para baixo na visualização.
        total_antes = len(self.itens)
        for coluna in range(qtd_colunas):
            x_coluna = round(
                x_min + coluna * (largura_coluna + self.espaco), 2
            )
            y_cursor = round(y_limite_inf, 2)
            for travessa in travessas:
                y_item = y_cursor
                if not self.cabe(
                    x_coluna, y_item, travessa["w"], travessa["h"]
                ):
                    raise ValueError(
                        f"A travessa '{travessa['nome']}' da seção"
                        f" '{nome_secao}' não pôde ser posicionada (x="
                        f"{fmt(x_coluna)}, y={fmt(y_item)}) por sobreposição"
                        f" com outros itens do balcão."
                    )
                self.itens.append(
                    {
                        "nome": travessa["nome"],
                        "x": x_coluna,
                        "y": y_item,
                        "w": travessa["w"],
                        "h": travessa["h"],
                        "formato": "retangulo",
                    }
                )
                y_cursor = round(y_cursor + travessa["h"] + self.espaco, 2)

        # Mesmo acabamento das demais seções: distribuição homogênea dos
        # gaps em X (entre colunas) e em Y (dentro de cada coluna),
        # preservando a ordem de cima para baixo e das colunas.
        self.otimizar_gaps_da_secao(
            total_antes, x_min, x_max, y_min=y_limite_inf, y_max=None
        )
