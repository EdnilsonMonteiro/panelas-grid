# modelos.py
from engine import LayoutEngine


class ModuloBalcao(LayoutEngine):
    def __init__(self, tipo_rampa, largura, profundidade, espacamento_cm=0.5):
        super().__init__(largura, profundidade, espacamento_cm)
        self.tipo_rampa = tipo_rampa

    def alocar_panelas_redondas_inteligente(self, qtd_desejada, x_min, x_max):
        """
        Calcula a melhor configuração vertical de diâmetro de panelas para o balcão
        antes de alocar, evitando o comportamento guloso horizontal.
        """
        diametros_permitidos = [34, 32, 30, 28, 26, 24, 22]

        melhor_diametro = diametros_permitidos[-1]
        melhor_linhas_por_coluna = 1
        melhor_aproveitamento_v = 0

        # Passo 1: Descobrir qual diâmetro e quantas linhas preenchem melhor a profundidade (P)
        for d in diametros_permitidos:
            # Testa quantas panelas desse diâmetro cabem empilhadas verticalmente
            for linhas in range(1, qtd_desejada + 1):
                altura_total = (linhas * d) + ((linhas - 1) * self.espaco)
                if altura_total <= self.P:
                    # Se o aproveitamento vertical for melhor que o anterior conhecido
                    if altura_total > melhor_aproveitamento_v:
                        melhor_aproveitamento_v = float(altura_total)
                        melhor_diametro = d
                        melhor_linhas_por_coluna = linhas

        print(
            f" -> Configuração de Panelas Escolhida: Ø{melhor_diametro}cm disposto em {melhor_linhas_por_coluna} linha(s) vertical(is)"
        )

        # Passo 2: Alocar seguindo estritamente a estratégia de colunas verticais encontrada
        alocadas = 0
        x_atual = x_min

        while alocadas < qtd_desejada:
            itens_da_coluna = []
            y_atual = 0.0

            # Tenta montar uma coluna vertical completa com o diâmetro ideal escolhido
            for l in range(melhor_linhas_por_coluna):
                if alocadas + len(itens_da_coluna) >= qtd_desejada:
                    break

                nome = (
                    "Arroz" if (alocadas + len(itens_da_coluna)) % 2 == 0 else "Feijão"
                )

                # Verifica se cabe nesta coordenada específica da varredura
                if self.cabe(x_atual, y_atual, melhor_diametro, melhor_diametro) and (
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
                    y_atual += melhor_diametro + self.espaco
                else:
                    break

            # Se conseguimos colocar itens nessa coluna, consolida e avança no eixo X
            if itens_da_coluna:
                self.itens.extend(itens_da_coluna)
                alocadas += len(itens_da_coluna)
                # Avança o X para a próxima coluna baseando-se na largura real do diâmetro usado
                x_atual += melhor_diametro + self.espaco
            else:
                # Se não coube nem a primeira panela da coluna no X atual, tenta usar os passos normais do BL
                passos_x = sorted(
                    list(
                        set(
                            [
                                round(i["x"] + i["w"] + self.espaco, 2)
                                for i in self.itens
                                if i["x"] >= x_atual
                            ]
                        )
                    )
                )
                if passos_x:
                    x_atual = passos_x[0]
                else:
                    break  # Sem espaço horizontal restante na seção

        print(f" > Panelas Redondas Alocadas: {alocadas}/{qtd_desejada}")
        return alocadas


class PedidoCliente:
    def __init__(self, nome_cliente):
        self.nome_cliente = nome_cliente
        self.modulos = []

    def adicionar_modulo(self, tipo_rampa, largura, profundidade, espacamento_cm=0.5):
        modulo = ModuloBalcao(tipo_rampa, largura, profundidade, espacamento_cm)
        self.modulos.append(modulo)
        return modulo
