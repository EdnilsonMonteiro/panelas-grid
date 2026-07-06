import copy
from abc import ABC, abstractmethod


class Secao(ABC):
    """Classe base abstrata (contrato) para qualquer tipo de seção."""

    def __init__(self, nome, pct_largura_alvo=1.0):
        self.nome = nome
        self.pct_largura_alvo = pct_largura_alvo

    @abstractmethod
    def executar_alocacao(self, modulo, x_min, x_max, catalogo):
        """Método que cada seção implementará com sua própria regra geométrica."""
        pass


class SecaoTorresGulosas(Secao):
    """
    Preenche a seção criando torres verticais de forma gulosa (greedy).
    Pega a maior travessa daquela largura, empilha até não caber mais,
    e então tenta a próxima maior para preencher o resto da coluna.
    """

    UI_SCHEMA = {
        "tipo": "SecaoTorresGulosas",
        "nome_amigavel": "Preenchimento Guloso (Rápido)",
        "descricao": "Preenche o espaço tentando alocar as maiores travessas primeiro.",
        "campos": [
            {"nome": "catalogo", "tipo": "catalogo", "label": "Catálogo de Travessas"},
            {
                "nome": "pct_largura_alvo",
                "tipo": "float",
                "label": "% do Espaço Restante",
                "default": 0.7,
            },
        ],
    }

    def __init__(self, nome, pct_largura_alvo=0.7, catalogo=None, **kwargs):
        super().__init__(nome, pct_largura_alvo)
        self.catalogo_especifico = catalogo

    def buscar_torres_gulosas(self, catalogo, altura_maxima, espaco):
        catalogo_isolado = copy.deepcopy(catalogo)
        itens_por_largura = {}

        for item in catalogo_isolado:
            w, h = item["w"], item["h"]
            if w not in itens_por_largura:
                itens_por_largura[w] = []
            itens_por_largura[w].append(item)

            if item.get("rot", False) and w != h:
                if h not in itens_por_largura:
                    itens_por_largura[h] = []
                itens_por_largura[h].append(
                    {"nome": item["nome"] + " (R)", "w": h, "h": w}
                )

        torres_gulosas = []

        for lw, itens_disponiveis in itens_por_largura.items():
            itens_disponiveis = sorted(
                itens_disponiveis, key=lambda x: x["h"], reverse=True
            )

            itens_da_torre = []
            altura_ocupada = 0.0

            # LÓGICA GULOSA:
            # Tenta a maior peça. Se couber, repete. Se não, vai pra próxima.
            for item in itens_disponiveis:
                while True:
                    espaco_extra = espaco if itens_da_torre else 0
                    altura_projetada = altura_ocupada + espaco_extra + item["h"]

                    if altura_projetada <= altura_maxima:
                        itens_da_torre.append(item)
                        altura_ocupada = altura_projetada
                    else:
                        break

            if itens_da_torre:
                torres_gulosas.append(
                    {
                        "largura": lw,
                        "itens": itens_da_torre,
                        "aproveitamento": altura_ocupada,
                    }
                )

        torres_gulosas = sorted(
            torres_gulosas, key=lambda x: x["aproveitamento"], reverse=True
        )

        print(f"Torres gulosas calculadas para a seção: {self.nome}")
        return torres_gulosas

    def executar_alocacao(self, modulo, x_min, x_max, catalogo):
        cat_para_usar = (
            self.catalogo_especifico if self.catalogo_especifico else catalogo
        )

        torres = self.buscar_torres_gulosas(
            cat_para_usar, altura_maxima=modulo.engine.P, espaco=modulo.engine.espaco
        )

        modulo.engine.preencher_secao_com_torres(
            torres, x_min=x_min, x_max=x_max, nome_secao=self.nome
        )


class SecaoMioloTorres(Secao):
    """Encapsula a otimização vertical pura de torres de cubas"""

    UI_SCHEMA = {
        "tipo": "SecaoMioloTorres",
        "nome_amigavel": "Otimização de Torres (Miolo)",
        "descricao": "Calcula combinações verticais complexas para maximizar matematicamente a altura utilizada do balcão.",
        "campos": [
            {"nome": "catalogo", "tipo": "catalogo", "label": "Catálogo de Cubas"},
            {
                "nome": "pct_largura_alvo",
                "tipo": "float",
                "label": "% do Espaço Restante",
                "default": 0.7,
            },
        ],
    }

    def __init__(self, nome, pct_largura_alvo=0.7, **kwargs):
        super().__init__(nome, pct_largura_alvo)

    def buscar_melhor_combinacao_vertical(self, catalogo, altura_maxima, espaco):
        """Busca combinações verticais maximizando a altura usada."""
        catalogo_isolado = copy.deepcopy(catalogo)
        print("Catálogo Utilizado:")
        print(catalogo_isolado)
        itens_por_largura = {}
        for item in catalogo_isolado:
            w, h = item["w"], item["h"]
            if w not in itens_por_largura:
                itens_por_largura[w] = []
            itens_por_largura[w].append(item)
            if item.get("rot", False) and w != h:
                if h not in itens_por_largura:
                    itens_por_largura[h] = []
                itens_por_largura[h].append(
                    {"nome": item["nome"] + " (R)", "w": h, "h": w}
                )

        melhores_torres = []

        for lw, itens_disponiveis in itens_por_largura.items():
            # itens_disponiveis contém os tipos únicos de cubas daquela largura (ex: M, Meio, P)
            melhor_soma = 0
            melhor_combinacao = []
            maior_peca_da_comb = 0

            def encontrar_comb(soma_atual, comb_atual):
                nonlocal melhor_soma, melhor_combinacao, maior_peca_da_comb

                qtd_gaps = len(comb_atual) - 1
                custo_espaco = max(0, qtd_gaps * espaco)
                total_com_espaco = soma_atual + custo_espaco

                # Se estourar a altura do balcão (95cm), interrompe esta ramificação
                if total_com_espaco > altura_maxima:
                    return

                peca_max_atual = max([x["h"] for x in comb_atual]) if comb_atual else 0

                # Verifica se esta combinação é melhor do que a encontrada anteriormente
                if (total_com_espaco > melhor_soma) or (
                    abs(total_com_espaco - melhor_soma) < 0.1
                    and peca_max_atual > maior_peca_da_comb
                ):
                    melhor_soma = total_com_espaco
                    melhor_combinacao = list(comb_atual)
                    maior_peca_da_comb = peca_max_atual

                # PERMISSÃO DE STOCK INFINITO: Sempre varre TODOS os tipos disponíveis
                # permitindo acumular múltiplas cubas do mesmo tamanho (ex: 3 Cubas P)
                for item in itens_disponiveis:
                    comb_atual.append(item)
                    encontrar_comb(soma_atual + item["h"], comb_atual)
                    comb_atual.pop()

            encontrar_comb(0, [])
            if melhor_combinacao:
                melhores_torres.append(
                    {
                        "largura": lw,
                        "itens": melhor_combinacao,
                        "aproveitamento": melhor_soma,
                    }
                )

        melhores_torres = sorted(
            melhores_torres, key=lambda x: x["aproveitamento"], reverse=True
        )
        print("Melhores torres calculadas")
        print(melhores_torres)
        return melhores_torres

    def executar_alocacao(self, modulo, x_min, x_max, catalogo):
        torres_miolo = self.buscar_melhor_combinacao_vertical(
            catalogo, altura_maxima=modulo.engine.P, espaco=modulo.engine.espaco
        )
        modulo.engine.preencher_secao_com_torres(
            torres_miolo, x_min=x_min, x_max=x_max, nome_secao=self.nome
        )


class SecaoPanelasRedondasComGaps(SecaoMioloTorres):
    """Encapsula as panelas redondas e o preenchimento de gaps abaixo delas."""

    UI_SCHEMA = {
        "tipo": "SecaoPanelasRedondasComGaps",
        "nome_amigavel": "Panelas Redondas + Gaps",
        "descricao": "Aloca panelas redondas e preenche o espaço inferior com torres.",
        "campos": [
            {
                "nome": "catalogo_gaps",
                "tipo": "catalogo",
                "label": "Catálogo para Gaps",
            },
            {
                "nome": "qtd_panelas",
                "tipo": "int",
                "label": "Quantidade de Panelas",
                "default": 6,
            },
            {
                "nome": "pct_largura_alvo",
                "tipo": "float",
                "label": "% do Espaço Restante",
                "default": 0.3,
            },
        ],
    }

    def __init__(
        self, nome, qtd_panelas=4, catalogo_gaps=None, pct_largura_alvo=0.8, **kwargs
    ):
        self.qtd_panelas = qtd_panelas
        self.catalogo_gaps = catalogo_gaps

        super().__init__(nome=nome, pct_largura_alvo=pct_largura_alvo, **kwargs)

    def executar_alocacao(self, modulo, x_min, x_max, catalogo):
        self.alocar_panelas_redondas_inteligente(
            engine=modulo.engine,
            qtd_desejada=self.qtd_panelas,
            x_min=x_min,
            x_max=x_max,
        )
        limite_fisico_s1 = modulo.engine.obter_limite_direito()

        altura_restante_s1 = modulo.engine.P - 34.0

        torres_s1 = self.buscar_melhor_combinacao_vertical(
            self.catalogo_gaps,
            altura_maxima=altura_restante_s1,
            espaco=modulo.engine.espaco,
        )

        modulo.engine.preencher_secao_com_torres(
            torres_s1, x_min=x_min, x_max=limite_fisico_s1, nome_secao=self.nome
        )

    def alocar_panelas_redondas_inteligente(self, engine, qtd_desejada, x_min, x_max):
        diametros_permitidos = [34, 32, 30, 28, 26, 24, 22]
        melhor_diametro = diametros_permitidos[-1]
        melhor_linhas_por_coluna = 1
        melhor_aproveitamento_v = 0

        for d in diametros_permitidos:
            for linhas in range(1, qtd_desejada + 1):
                altura_total = (linhas * d) + ((linhas - 1) * engine.espaco)
                if altura_total <= engine.P:
                    if altura_total > melhor_aproveitamento_v:
                        melhor_aproveitamento_v = float(altura_total)
                        melhor_diametro = d
                        melhor_linhas_por_coluna = linhas

        print(
            f" -> Configuração de Panelas Escolhida: Ø{melhor_diametro}cm disposto em {melhor_linhas_por_coluna} linha(s)"
        )

        alocadas = 0
        x_atual = x_min

        while alocadas < qtd_desejada:
            itens_da_coluna = []
            y_atual = 0.0

            for l in range(melhor_linhas_por_coluna):
                if alocadas + len(itens_da_coluna) >= qtd_desejada:
                    break
                nome = (
                    "Arroz" if (alocadas + len(itens_da_coluna)) % 2 == 0 else "Feijão"
                )

                if engine.cabe(x_atual, y_atual, melhor_diametro, melhor_diametro) and (
                    x_atual + melhor_diametro <= x_max
                ):
                    itens_da_coluna.append(
                        {
                            "nome": f"{nome} {alocadas + len(itens_da_coluna) + 1}",
                            "x": x_atual,
                            "y": y_atual,
                            "w": melhor_diametro,
                            "h": melhor_diametro,
                            "formato": "circulo",
                        }
                    )
                    y_atual += melhor_diametro + engine.espaco
                else:
                    break

            if itens_da_coluna:
                engine.itens.extend(itens_da_coluna)
                alocadas += len(itens_da_coluna)
                x_atual += melhor_diametro + engine.espaco
            else:
                passos_x = sorted(
                    list(
                        set(
                            [
                                round(i["x"] + i["w"] + engine.espaco, 2)
                                for i in engine.itens
                                if i["x"] >= x_atual
                            ]
                        )
                    )
                )
                if passos_x:
                    x_atual = passos_x[0]
                else:
                    break

        print(f" > Panelas Redondas Alocadas: {alocadas}/{qtd_desejada}")
        return alocadas


class SecaoItensFixos(Secao):
    """Encapsula o preenchimento de itens específicos/saladas"""

    UI_SCHEMA = {
        "tipo": "SecaoItensFixos",
        "nome_amigavel": "Itens Fixos / Saladas",
        "descricao": "Aloca uma lista predefinida de itens específicos (como saladas ou travessas dedicadas) sem otimização combinatória.",
        "campos": [
            {
                "nome": "catalogo_especifico",
                "tipo": "catalogo",
                "label": "Catálogo de Itens Fixos",
            },
            {
                "nome": "pct_largura_alvo",
                "tipo": "float",
                "label": "% do Espaço Restante",
                "default": 1.0,
            },
        ],
    }

    def __init__(self, nome, catalogo_especifico=None, pct_largura_alvo=1.0, **kwargs):
        self.catalogo_especifico = catalogo_especifico

        super().__init__(nome=nome, pct_largura_alvo=pct_largura_alvo)

    def executar_alocacao(self, modulo, x_min, x_max, catalogo):
        cat_para_usar = (
            self.catalogo_especifico if self.catalogo_especifico else catalogo
        )

        modulo.engine.preencher_secao(
            cat_para_usar, x_min=x_min, x_max=x_max, nome_secao=self.nome
        )
