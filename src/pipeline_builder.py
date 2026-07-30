"""Construção do pipeline de layout a partir do JSON enviado pela UI.

Módulo compartilhado pelos serviços da API, mantendo uma única fonte de
verdade para a orquestração do motor geométrico.
"""

from modules.catalogos.catalogo_service import carregar_catalogo_por_nome
from secoes import (
    SecaoItensFixos,
    SecaoMioloTorres,
    SecaoPanelasRedondasComGaps,
    SecaoTorresGulosas,
)

REGISTRO_SECOES = {
    "SecaoTorresGulosas": SecaoTorresGulosas,
    "SecaoPanelasRedondasComGaps": SecaoPanelasRedondasComGaps,
    "SecaoMioloTorres": SecaoMioloTorres,
    "SecaoItensFixos": SecaoItensFixos,
}


def construir_pipeline_desde_json(json_config, pedido):
    conf_balcao = json_config["configuracao_balcao"]

    cat_completo_global = carregar_catalogo_por_nome("catalogo_mestre")
    espacamento_ui = conf_balcao.get("espaco", 0.5)
    print(f"Espaçamento UI: {espacamento_ui}")

    modulo = pedido.adicionar_modulo(
        tipo_rampa="quente",
        largura=conf_balcao["L"],
        profundidade=conf_balcao["P"],
        espacamento_cm=float(espacamento_ui),
    )

    for config_secao in json_config["pipeline_secoes"]:
        tipo_classe = config_secao["tipo"]
        nome_instancia = config_secao["nome"]
        pct_alvo = config_secao.get("pct_largura_alvo", 1.0)
        params = config_secao.get("parametros", {})

        ClasseSecao = REGISTRO_SECOES.get(tipo_classe)
        if not ClasseSecao:
            raise ValueError(f"Classe de seção desconhecida: {tipo_classe}")

        kwargs_init = {"nome": nome_instancia, "pct_largura_alvo": pct_alvo}

        for chave, valor in params.items():
            if "catalogo" in chave:
                if isinstance(valor, str):
                    lista_cuba = carregar_catalogo_por_nome(valor)

                elif isinstance(valor, list):
                    lista_cuba = valor
                else:
                    lista_cuba = []

                kwargs_init[chave] = lista_cuba

                if chave == "catalogo":
                    kwargs_init["catalogo_especifico"] = lista_cuba
            else:
                kwargs_init[chave] = valor

        instancia_secao = ClasseSecao(**kwargs_init)

        if (
            not hasattr(instancia_secao, "pct_largura_alvo")
            or instancia_secao.pct_largura_alvo != pct_alvo
        ):
            instancia_secao.pct_largura_alvo = pct_alvo

        modulo.adicionar_secao(instancia_secao)

    modulo.processar_layout(cat_completo_global)

    return pedido
