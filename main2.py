from exportadores import ExportadorPDF
from modelos import PedidoCliente

print("\n=== PROCESSANDO PEDIDO COM OTIMIZAÇÃO DE COLUNA ===")
pedido_combo = PedidoCliente("Combo Rampa Quente e Fria")

# 1. Rampa Quente (200cm x 50cm)
rampa_quente = pedido_combo.adicionar_modulo(
    tipo_rampa="quente", largura=200, profundidade=50
)

# Proteção da Seção 4 (Extremidade Direita Fixa)
largura_s4 = 35.0
x_min_s4 = rampa_quente.L - largura_s4
x_max_s4 = rampa_quente.L

# Executa Seção 1 (Panelas Redondas - Limitadas a Max Ø30)
rampa_quente.alocar_panelas_redondas_inteligente(
    qtd_desejada=4, x_min=0, x_max=x_min_s4
)

# Define o Miolo Dinâmico (Seções 2 e 3) com base no final real da Seção 1
fim_real_s1 = rampa_quente.obter_limite_direito()
x_min_miolo = fim_real_s1 + rampa_quente.espaco
x_max_miolo = x_min_s4 - rampa_quente.espaco

# Catálogo completo solicitado para teste de aproximação perfeita na profundidade de 50cm
cat_completo = [
    {"nome": "Cuba 21x44", "w": 21, "h": 44, "rot": True},
    {"nome": "Cuba 21x32", "w": 21, "h": 32, "rot": True},
    {"nome": "Cuba 21x21", "w": 21, "h": 21},
    {"nome": "Cuba 21x13", "w": 21, "h": 13, "rot": True},
    {"nome": "Cuba 17x44", "w": 17, "h": 44, "rot": True},
    {"nome": "Cuba 13x42", "w": 13, "h": 42, "rot": True},
    {
        "nome": "Cuba 21x53",
        "w": 21,
        "h": 53,
        "rot": True,
    },  # Essa não vai caber direta se P=50, mas testa rotação
    {"nome": "Cuba 32x45", "w": 32, "h": 45, "rot": True},
]

if x_max_miolo > x_min_miolo:
    # CHAMA O NOVO MÉTODO OTIMIZADO
    rampa_quente.preencher_secao_otimizada(
        cat_completo,
        x_min=x_min_miolo,
        x_max=x_max_miolo,
        nome_secao="Miolo Otimizado (Seções 2 e 3)",
    )

# Preenchimento da Seção 4 Protegida
rampa_quente.preencher_secao_otimizada(
    cat_completo, x_min=x_min_s4, x_max=x_max_s4, nome_secao="Seção 4 Final"
)

# Salva e confere o resultado visual perfeito
ExportadorPDF.gerar_layout(pedido_combo, "layout_otimizado_mochila.pdf")
