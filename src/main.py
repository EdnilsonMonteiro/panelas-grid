from exportadores.pdf import ExportadorPDF
from exportadores.pptx import ExportadorPPTX
from modelos import PedidoCliente
from secoes import SecaoItensFixos, SecaoMioloTorres, SecaoPanelasRedondasComGaps

print("\n=== PROCESSANDO PEDIDO - ENGENHARIA DE LAYOUT POR SEÇÕES ===")
pedido_combo = PedidoCliente("Combo Rampa Otimizada")

cat_completo = [
    {"nome": "Cuba G", "w": 21, "h": 53, "rot": True},
    {"nome": "Cuba M", "w": 21, "h": 32, "rot": True},
    {"nome": "Cuba Meio", "w": 21, "h": 21},
    {"nome": "Cuba P", "w": 21, "h": 13, "rot": True},
    {"nome": "Cuba Slim", "w": 17, "h": 44, "rot": True},
    {"nome": "Cuba Mini", "w": 13, "h": 42, "rot": True},
    {"nome": "Cuba Quadrada", "w": 32, "h": 45, "rot": True},
]

cat_s4 = [
    {"nome": "Salada Prin.", "w": 21, "h": 32},
    {"nome": "Fina", "w": 13, "h": 32, "rot": True},
    {"nome": "Guarnição M", "w": 21, "h": 21},
    {"nome": "Guarnição P", "w": 21, "h": 13, "rot": True},
]

balcao_grande = pedido_combo.adicionar_modulo(
    tipo_rampa="quente", largura=190, profundidade=95
)

balcao_grande.adicionar_secao(
    SecaoPanelasRedondasComGaps(
        nome="Seção 1: Redondas", qtd_panelas=6, catalogo_gaps=cat_completo
    )
).adicionar_secao(SecaoMioloTorres(nome="Seções 2+3: Miolo Central")).adicionar_secao(
    SecaoItensFixos(nome="Seção 4: Final Especial", catalogo_especifico=cat_s4)
)

balcao_grande.processar_layout(cat_completo)

# =========================================================================
# CENÁRIO 2: O caso dos 4 grids menores independentes (Ex: 75x50)
# =========================================================================
# for i in range(4):
#    grid_pequeno = pedido_combo.adicionar_modulo(
#        tipo_rampa="quente", largura=75, profundidade=50
#    )
#
# Cada grid pode receber uma combinação totalmente diferente de seções!
#    grid_pequeno.adicionar_secao(SecaoMioloTorres(nome=f"Grid {i + 1} - Apenas Cubas"))
#    grid_pequeno.processar_layout(cat_completo)

ExportadorPDF.gerar_layout(pedido_combo, "layout_otimizado_generico.pdf")
ExportadorPPTX.gerar_layout(pedido_combo, "layout_otimizado_editavel.pptx")
