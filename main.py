# main.py
from exportadores.pdf import ExportadorPDF
from exportadores.pptx import ExportadorPPTX
from modelos import PedidoCliente

print("\n=== PROCESSANDO PEDIDO - ALOCAÇÃO INTELIGENTE GENÉRICA ===")
pedido_combo = PedidoCliente("Combo Rampa Otimizada")

# Instancia o módulo (funciona dinamicamente mudando largura ou profundidade)
rampa = pedido_combo.adicionar_modulo(tipo_rampa="quente", largura=190, profundidade=95)

PCT_FIM_SECOES_1_2_3 = 0.75
limite_secoes_2_3 = round(rampa.L * PCT_FIM_SECOES_1_2_3, 2)

# Catálogo mestre do sistema (pode conter qualquer item)
cat_completo = [
    {"nome": "Cuba G", "w": 21, "h": 53, "rot": True},
    {"nome": "Cuba M", "w": 21, "h": 32, "rot": True},
    {"nome": "Cuba Meio", "w": 21, "h": 21},
    {"nome": "Cuba P", "w": 21, "h": 13, "rot": True},
    {"nome": "Cuba Slim", "w": 17, "h": 44, "rot": True},
    {"nome": "Cuba Mini", "w": 13, "h": 42, "rot": True},
    {"nome": "Cuba Quadrada", "w": 32, "h": 45, "rot": True},
]

# --- PASSO 1: ALOCAÇÃO DAS PANELAS REDONDAS ---
rampa.alocar_panelas_redondas_inteligente(
    qtd_desejada=6, x_min=0, x_max=limite_secoes_2_3
)
limite_fisico_s1 = rampa.obter_limite_direito()

# --- PASSO 2: PREENCHIMENTO DOS GAPS DA SEÇÃO 1 (Abaixo das Panelas) ---
altura_restante_s1 = rampa.P - 34.0
torres_s1 = rampa.buscar_melhor_combinacao_vertical(
    cat_completo, altura_maxima=altura_restante_s1
)

rampa.preencher_secao_com_torres(
    torres_s1, x_min=0, x_max=limite_fisico_s1, nome_secao="Tapa Buracos Seção 1"
)

# --- PASSO 3: SEÇÕES 2 E 3 (Miolo com Otimização de Torres Integras) ---
torres_miolo = rampa.buscar_melhor_combinacao_vertical(
    cat_completo, altura_maxima=rampa.P
)

x_start_s2 = rampa.obter_limite_direito() + rampa.espaco
rampa.preencher_secao_com_torres(
    torres_miolo,
    x_min=x_start_s2,
    x_max=limite_secoes_2_3,
    nome_secao="Miolo Seções 2+3",
)

# --- PASSO 4: SEÇÃO 4 (Itens Distintos Fixos) ---
cat_s4 = [
    {"nome": "Salada Prin.", "w": 21, "h": 32},
    {"nome": "Fina", "w": 13, "h": 32, "rot": True},
    {"nome": "Guarnição M", "w": 21, "h": 21},
    {"nome": "Guarnição P", "w": 21, "h": 13, "rot": True},
]

x_start_s4 = rampa.obter_limite_direito() + rampa.espaco
rampa.preencher_secao(
    cat_s4, x_min=x_start_s4, x_max=rampa.L, nome_secao="Seção 4 Final"
)

# --- EXPORTAÇÃO DUPLA ---
# 1. Mantém a geração clássica do relatório em PDF
ExportadorPDF.gerar_layout(pedido_combo, "layout_otimizado_generico.pdf")

# 2. Executa a nova geração do arquivo editável do PowerPoint
ExportadorPPTX.gerar_layout(pedido_combo, "layout_otimizado_editavel.pptx")
