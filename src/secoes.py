import copy
import math
from abc import ABC, abstractmethod


class Secao(ABC):
    """Classe base abstrata (contrato) para qualquer tipo de seção."""

    def __init__(self, nome, pct_largura_alvo=1.0):
        self.nome = nome
        self.pct_largura_alvo = pct_largura_alvo
        self.pista = "quente"

    def buscar_melhor_combinacao_vertical(self, catalogo, altura_maxima, espaco):
        """Busca combinações verticais maximizando a altura usada de forma precisa."""
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

        melhores_torres = []

        for lw, itens_disponiveis in itens_por_largura.items():
            melhor_soma = 0.0
            melhor_combinacao = []
            maior_peca_da_comb = 0.0

            def encontrar_comb(soma_atual, comb_atual):
                nonlocal melhor_soma, melhor_combinacao, maior_peca_da_comb

                qtd_gaps = len(comb_atual) - 1
                custo_espaco = max(0, qtd_gaps * espaco)
                total_com_espaco = round(soma_atual + custo_espaco, 2)

                if total_com_espaco > altura_maxima:
                    return

                peca_max_atual = (
                    max([x["h"] for x in comb_atual]) if comb_atual else 0.0
                )

                # CORREÇÃO: Tolerância de float ajustada com round nas comparações
                if (total_com_espaco > melhor_soma) or (
                    abs(round(total_com_espaco - melhor_soma, 2)) < 0.01
                    and peca_max_atual > maior_peca_da_comb
                ):
                    melhor_soma = total_com_espaco
                    melhor_combinacao = list(comb_atual)
                    maior_peca_da_comb = peca_max_atual

                for item in itens_disponiveis:
                    comb_atual.append(item)
                    encontrar_comb(soma_atual + item["h"], comb_atual)
                    comb_atual.pop()

            encontrar_comb(0.0, [])
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
        return melhores_torres

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

            for item in itens_disponiveis:
                while True:
                    espaco_extra = espaco if itens_da_torre else 0.0
                    # CORREÇÃO: Aplica round direto na projeção da soma
                    altura_projetada = round(
                        altura_ocupada + espaco_extra + item["h"], 2
                    )

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
        return torres_gulosas

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
        self.catalogo_especifico = kwargs.get("catalogo", None)

    def executar_alocacao(self, modulo, x_min, x_max, catalogo):
        if isinstance(self.catalogo_especifico, str) and isinstance(catalogo, dict):
            cat_para_usar = catalogo.get(self.catalogo_especifico, catalogo)
        else:
            cat_para_usar = (
                self.catalogo_especifico if self.catalogo_especifico else catalogo
            )

        torres_miolo = self.buscar_melhor_combinacao_vertical(
            cat_para_usar, altura_maxima=modulo.engine.P, espaco=modulo.engine.espaco
        )

        modulo.engine.preencher_secao_com_torres(
            torres_miolo, x_min=x_min, x_max=x_max, nome_secao=self.nome
        )


class SecaoPanelasRedondasComGaps(Secao):
    """Encapsula as panelas redondas e o preenchimento de gaps abaixo delas dinamicamente."""

    UI_SCHEMA = {
        "tipo": "SecaoPanelasRedondasComGaps",
        "nome_amigavel": "Panelas Redondas + Gaps Dinâmicos",
        "descricao": "Aloca panelas baseadas em catálogo e preenche o espaço inferior com cubas.",
        "campos": [
            {
                "nome": "catalogo_panelas",
                "tipo": "catalogo",
                "label": "Catálogo de Panelas Redondas",
                "default": "panelas_redondas",
            },
            {
                "nome": "catalogo_gaps",
                "tipo": "catalogo",
                "label": "Catálogo para Gaps (Cubas)",
                "default": "catalogo_gaps",
            },
            {
                "tipo": "select",
                "nome": "estrategia_gaps",
                "label": "Estratégia de Preenchimento",
                "default": "combinacao_eficiente",
                "options": [
                    {
                        "value": "combinacao_eficiente",
                        "label": "Combinação Vertical Eficiente",
                    },
                    {"value": "torres_gulosas", "label": "Torres Gulosas (Rápido)"},
                    {"value": "itens_fixos", "label": "Sequência de Itens Fixos"},
                ],
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
        self,
        nome,
        qtd_panelas=4,
        catalogo_panelas=None,
        catalogo_gaps=None,
        pct_largura_alvo=0.8,
        estrategia_gaps="combinacao_eficiente",
        **kwargs,
    ):
        self.qtd_panelas = qtd_panelas
        self.catalogo_panelas = catalogo_panelas or []
        self.catalogo_gaps = catalogo_gaps or []
        self.estrategia_gaps = estrategia_gaps

        super().__init__(nome=nome, pct_largura_alvo=pct_largura_alvo, **kwargs)

    def _obter_diametros_permitidos(self):
        """Extrai os diâmetros únicos do catálogo de panelas, ordenando do maior para o menor."""
        if not self.catalogo_panelas:
            # Fallback de segurança caso o catálogo venha vazio
            return [34, 32, 30, 28, 26, 24, 22]

        diametros = set()
        for item in self.catalogo_panelas:
            # Aceita chaves flexíveis do JSON ('diametro', 'w' ou 'largura')
            d = item.get("diametro", item.get("w", item.get("largura", 0)))
            if d > 0:
                diametros.add(float(d))

        return sorted(list(diametros), reverse=True)

    def _calcular_altura_minima_gaps(self):
        """
        Analisa o catálogo de cubas e descobre qual é a menor altura física que uma peça
        consegue ocupar na grade vertical, considerando a possibilidade de rotação.
        """
        if not self.catalogo_gaps:
            return 13.0  # Fallback de segurança caso não existam cubas cadastradas

        alturas_possiveis = []
        for item in self.catalogo_gaps:
            w = float(item.get("w", item.get("largura", 0)))
            h = float(item.get("h", item.get("altura", 0)))
            pode_rotacionar = item.get("rotacionar", True)

            if w <= 0 or h <= 0:
                continue

            if pode_rotacionar:
                # Se pode rotacionar, o menor lado pode virar a altura
                alturas_possiveis.append(min(w, h))
            else:
                # Se não pode rotacionar, a altura estrita é 'h'
                alturas_possiveis.append(h)

        return min(alturas_possiveis) if alturas_possiveis else 13.0

    def executar_alocacao(self, modulo, x_min, x_max, catalogo):
        # 1. Executa a alocação e captura qual foi o diâmetro efetivamente escolhido pelo algoritmo
        melhor_diametro, melhor_linhas = self.alocar_panelas_redondas_inteligente(
            engine=modulo.engine,
            qtd_desejada=self.qtd_panelas,
            x_min=x_min,
            x_max=x_max,
        )

        limite_fisico_s1 = modulo.engine.obter_limite_direito()

        # Se usamos 2 linhas de panela, a altura ocupada é (2 * d) + espaco
        altura_ocupada_panelas = (melhor_linhas * melhor_diametro) + (
            (melhor_linhas - 1) * modulo.engine.espaco
        )
        altura_restante_s1 = modulo.engine.P - altura_ocupada_panelas

        cat_para_gaps = self.catalogo_gaps if self.catalogo_gaps else catalogo

        estrategias = {
            "combinacao_eficiente": self._preencher_combinacao_vertical,
            "torres_gulosas": self._preencher_torres_gulosas,
            "itens_fixos": self._preencher_itens_fixos,
        }

        funcao_estrategia = estrategias.get(
            self.estrategia_gaps, self._preencher_combinacao_vertical
        )

        funcao_estrategia(
            modulo=modulo,
            catalogo=cat_para_gaps,
            altura_maxima=altura_restante_s1,
            x_min=x_min,
            x_max=limite_fisico_s1,
            altura_ocupada_panelas=altura_ocupada_panelas,
        )

    # --- Implementação das Estratégias (Isoladas e Limpas) ---
    def _preencher_combinacao_vertical(
        self, modulo, catalogo, altura_maxima, x_min, x_max, altura_ocupada_panelas
    ):
        torres = self.buscar_melhor_combinacao_vertical(
            catalogo, altura_maxima=altura_maxima, espaco=modulo.engine.espaco
        )
        # Passamos a linha de início e o fundo máximo como teto e piso
        modulo.engine.preencher_secao_com_torres(
            torres,
            x_min=x_min,
            x_max=x_max,
            nome_secao=self.nome,
            y_limite_inf=altura_ocupada_panelas,
            y_limite_sup=modulo.engine.P,
        )

    def _preencher_torres_gulosas(
        self, modulo, catalogo, altura_maxima, x_min, x_max, altura_ocupada_panelas
    ):
        torres = self.buscar_torres_gulosas(
            catalogo, altura_maxima=altura_maxima, espaco=modulo.engine.espaco
        )
        modulo.engine.preencher_secao_com_torres(
            torres,
            x_min=x_min,
            x_max=x_max,
            nome_secao=self.nome,
            y_limite_inf=altura_ocupada_panelas,
            y_limite_sup=modulo.engine.P,
        )

    def _preencher_itens_fixos(
        self, modulo, catalogo, altura_maxima, x_min, x_max, altura_ocupada_panelas
    ):
        modulo.engine.preencher_secao(
            catalogo,
            x_min=x_min,
            x_max=x_max,
            nome_secao=self.nome,
            y_limite_inf=altura_ocupada_panelas,
            y_limite_sup=modulo.engine.P,
        )

    def alocar_panelas_redondas_inteligente(self, engine, qtd_desejada, x_min, x_max):
        # Extração dinâmica de dados dos catálogos
        diametros_permitidos = self._obter_diametros_permitidos()
        altura_minima_gaps = self._calcular_altura_minima_gaps()

        largura_disponivel = x_max - x_min
        configuracoes_validas = []

        # Fase de Planejamento
        for d in diametros_permitidos:
            for linhas in range(1, qtd_desejada + 1):
                altura_total = (linhas * d) + ((linhas - 1) * engine.espaco)

                if altura_total > engine.P:
                    continue

                colunas_necessarias = math.ceil(qtd_desejada / linhas)
                largura_total = (colunas_necessarias * d) + (
                    (colunas_necessarias - 1) * engine.espaco
                )

                if largura_total <= largura_disponivel:
                    configuracoes_validas.append({"d": d, "linhas": linhas})

        # Fase de Decisão Baseada em Heurística Dinâmica
        if configuracoes_validas:

            def avaliar_configuracao(c):
                d = c["d"]
                linhas = c["linhas"]

                # Espaço morto que sobra verticalmente após colocar essa configuração de panelas
                altura_ocupada = (linhas * d) + ((linhas - 1) * engine.espaco)
                gap_restante = engine.P - altura_ocupada

                # REGRA DE OURO DINÂMICA:
                # Se as panelas são grandes (maiores que a média do catálogo), dispostas em 1 linha,
                # E o gap restante é suficiente para abrigar pelo menos a menor dimensão útil de cuba identificada.
                diametro_medio = sum(diametros_permitidos) / len(diametros_permitidos)

                if (
                    linhas == 1
                    and d >= diametro_medio
                    and gap_restante >= altura_minima_gaps
                ):
                    prioridade_layout = 3

                # REGRA SECUNDÁRIA:
                # Se colocar lado a lado não vai deixar espaço útil para cubas abaixo,
                # preferimos empilhar panelas menores (2 linhas) para usar a altura total.
                elif linhas == 2 and d < diametro_medio:
                    prioridade_layout = 2

                else:
                    prioridade_layout = 1

                return (prioridade_layout, d, -linhas)

            configuracoes_validas.sort(key=avaliar_configuracao, reverse=True)

            melhor_config = configuracoes_validas[0]
            melhor_diametro = melhor_config["d"]
            melhor_linhas_por_coluna = melhor_config["linhas"]
        else:
            # Fallback de segurança absoluto
            melhor_diametro = diametros_permitidos[-1]
            melhor_linhas_por_coluna = 1
            for d in diametros_permitidos:
                for linhas in range(1, qtd_desejada + 1):
                    if (linhas * d) + ((linhas - 1) * engine.espaco) <= engine.P:
                        melhor_diametro = d
                        melhor_linhas_por_coluna = linhas
                        break

        # Fase de Alocação Física na Engine
        alocadas = 0
        x_atual = x_min

        while alocadas < qtd_desejada:
            itens_da_coluna = []
            y_atual = 0.0

            for l in range(melhor_linhas_por_coluna):
                if alocadas + len(itens_da_coluna) >= qtd_desejada:
                    break

                nome_prato = (
                    "Arroz" if (alocadas + len(itens_da_coluna)) % 2 == 0 else "Feijão"
                )

                if engine.cabe(x_atual, y_atual, melhor_diametro, melhor_diametro) and (
                    round(x_atual + melhor_diametro, 2) <= round(x_max, 2)
                ):
                    itens_da_coluna.append(
                        {
                            "nome": f"{nome_prato} {alocadas + len(itens_da_coluna) + 1}",
                            "x": x_atual,
                            "y": y_atual,
                            "w": melhor_diametro,
                            "h": melhor_diametro,
                            "formato": "circulo",
                        }
                    )
                    y_atual = round(y_atual + melhor_diametro + engine.espaco, 2)
                else:
                    break

            if itens_da_coluna:
                engine.itens.extend(itens_da_coluna)
                alocadas += len(itens_da_coluna)
                # Avança a coluna X somando o diâmetro + o espaço configurado
                x_atual = round(x_atual + melhor_diametro + engine.espaco, 2)
            else:
                # Se não coube nesta coordenada X, pula para o próximo ponto disponível calculado pela engine
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

        return melhor_diametro, melhor_linhas_por_coluna


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
