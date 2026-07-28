from engine import LayoutEngine
from secoes import Secao


class ModuloBalcao:
    def __init__(self, tipo_rampa, largura, profundidade, espacamento_cm=0.5):
        self.tipo_rampa = tipo_rampa
        self.secoes = []
        self.engine = LayoutEngine(largura, profundidade, espacamento_cm)

    def adicionar_secao(self, secao: Secao):
        """Registra uma seção no balcão e retorna o próprio objeto (Fluent API)."""
        self.secoes.append(secao)
        return self

    def processar_layout(self, catalogo_mestre):
        """Percorre as seções calculando dinamicamente os limites x_min e x_max de cada uma."""
        x_atual = 0.0

        for i, secao in enumerate(self.secoes):
            # Se for a última seção, força ir até o limite total do balcão (self.L)
            if i == len(self.secoes) - 1:
                x_limite_secao = self.engine.L
            else:
                # Calcula a largura disponível restante e aplica o percentual alvo da seção
                largura_disponivel = self.engine.L - x_atual
                x_limite_secao = x_atual + (largura_disponivel * secao.pct_largura_alvo)

            print(secao)
            print(x_limite_secao)

            secao.executar_alocacao(
                modulo=self,
                x_min=x_atual,
                x_max=x_limite_secao,
                catalogo=catalogo_mestre,
            )
            print(
                f"DEBUG PÓS-{secao.nome}: Quantidade total de itens no balcão = {len(self.engine.itens)}"
            )

            # Atualiza o x_atual para a próxima seção começar após o último item inserido
            x_atual = self.engine.obter_limite_direito() + self.engine.espaco
            print(
                f"DEBUG PÓS-{secao.nome}: x_atual calculado para a próxima seção = {x_atual}"
            )


class PedidoCliente:
    def __init__(self, nome_cliente):
        self.nome_cliente = nome_cliente
        self.modulos = []

    def adicionar_modulo(self, tipo_rampa, largura, profundidade, espacamento_cm=0.5):
        modulo = ModuloBalcao(tipo_rampa, largura, profundidade, espacamento_cm)
        self.modulos.append(modulo)
        return modulo
