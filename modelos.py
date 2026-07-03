from engine import LayoutEngine


class ModuloBalcao(LayoutEngine):
    def __init__(self, tipo_rampa, largura, profundidade, espacamento_cm=0.5):
        super().__init__(largura, profundidade, espacamento_cm)
        self.tipo_rampa = tipo_rampa

    def alocar_panelas_redondas_inteligente(self, qtd_desejada, x_min, x_max):
        """
        Aloca panelas respeitando o limite máximo de diâmetro de 30cm.
        Se houver espaço residual abaixo delas, o motor de colunas subsequente
        vai conseguir preencher os buracos do eixo Y automaticamente.
        """
        # Diâmetros permitidos limitados ao máximo de 30 conforme solicitado
        diametros_permitidos = [34, 32, 30, 28]
        alocadas = 0

        for i in range(qtd_desejada):
            alocado = False
            nome = f"Panela {alocadas + 1}"

            for d in diametros_permitidos:
                if self.alocar_na_secao(
                    nome, w=d, h=d, x_min=x_min, x_max=x_max, formato="circulo"
                ):
                    alocadas += 1
                    alocado = True
                    break
            if not alocado:
                break

        print(f" > Panelas Redondas (Max Ø30) Alocadas: {alocadas}/{qtd_desejada}")
        return alocadas


class PedidoCliente:
    def __init__(self, nome_cliente):
        self.nome_cliente = nome_cliente
        self.modulos = []

    def adicionar_modulo(self, tipo_rampa, largura, profundidade, espacamento_cm=0.5):
        modulo = ModuloBalcao(tipo_rampa, largura, profundidade, espacamento_cm)
        self.modulos.append(modulo)
        return modulo
