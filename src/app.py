import json
import os
import zipfile

from flask import Flask, jsonify, request, send_file
from flask_cors import CORS

from exportadores.pdf import ExportadorPDF
from exportadores.pptx import ExportadorPPTX
from modelos import PedidoCliente
from secoes import (
    SecaoItensFixos,
    SecaoMioloTorres,
    SecaoPanelasRedondasComGaps,
    SecaoTorresGulosas,
)

app = Flask(__name__)
CORS(app)

REGISTRO_SECOES = {
    "SecaoTorresGulosas": SecaoTorresGulosas,
    "SecaoPanelasRedondasComGaps": SecaoPanelasRedondasComGaps,
    "SecaoMioloTorres": SecaoMioloTorres,
    "SecaoItensFixos": SecaoItensFixos,
}


def carregar_catalogo_por_nome(nome_catalogo: str) -> list:
    """Busca o arquivo de catálogo correspondente na pasta de catálogos."""
    caminho_pasta = os.path.join(os.path.dirname(__file__), "..", "catalogos")
    caminho_arquivo = os.path.join(caminho_pasta, f"{nome_catalogo}.json")

    if not os.path.exists(caminho_arquivo):
        # Fallback de segurança ou retorno de lista vazia caso não ache
        return []

    with open(caminho_arquivo, "r", encoding="utf-8") as f:
        return json.load(f)


def construir_pipeline_desde_json(json_config, pedido):
    conf_balcao = json_config["configuracao_balcao"]

    cat_completo_global = carregar_catalogo_por_nome("catalogo_mestre")

    modulo = pedido.adicionar_modulo(
        tipo_rampa="quente", largura=conf_balcao["L"], profundidade=conf_balcao["P"]
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
                lista_cuba = carregar_catalogo_por_nome(valor)
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


# --- ENDPOINTS DA API ---


@app.route("/api/catalogos", methods=["GET"])
def listar_catalogos():
    """Retorna os nomes de todos os arquivos de catálogos disponíveis para a UI."""
    caminho_pasta = os.path.join(os.path.dirname(__file__), "..", "catalogos")
    if not os.path.exists(caminho_pasta):
        return jsonify(["catalogo_mestre", "catalogo_gaps", "catalogo_saladas"])

    arquivos = [
        f.replace(".json", "") for f in os.listdir(caminho_pasta) if f.endswith(".json")
    ]
    return jsonify(arquivos)


@app.route("/api/schemas", methods=["GET"])
def obter_schemas_secoes():
    """Varre as seções registradas extraindo dinamicamente o UI_SCHEMA de cada uma."""
    schemas = []
    for classe in REGISTRO_SECOES.values():
        if hasattr(classe, "UI_SCHEMA"):
            schemas.append(classe.UI_SCHEMA)
    return jsonify(schemas)


@app.route("/api/processar", methods=["POST"])
def processar_pipeline():
    """Recebe a estrutura de montagem e retorna o arquivo de resposta gerado."""
    try:
        dados_recebidos = request.json
        if not dados_recebidos:
            return jsonify({"erro": "Payload JSON ausente ou inválido"}), 400

        nome_cliente_ui = dados_recebidos.get("nome_cliente", "Cliente Não Informado")
        if not nome_cliente_ui.strip():
            nome_cliente_ui = "Cliente Não Informado"

        pedido = PedidoCliente(nome_cliente=nome_cliente_ui)

        pedido_processado = construir_pipeline_desde_json(dados_recebidos, pedido)

        caminho_pdf = f"layouts_{nome_cliente_ui}.pdf"
        caminho_pptx = f"layouts_{nome_cliente_ui}.pptx"
        caminho_zip = f"layouts_{nome_cliente_ui}.zip"

        ExportadorPDF.gerar_layout(pedido_processado, caminho_pdf)
        ExportadorPPTX.gerar_layout(pedido_processado, caminho_pptx)

        nome_slug = nome_cliente_ui.replace(" ", "_").lower()

        with zipfile.ZipFile(caminho_zip, "w", zipfile.ZIP_DEFLATED) as zipf:
            zipf.write(caminho_pdf, arcname=f"layout_{nome_slug}.pdf")
            zipf.write(caminho_pptx, arcname=f"layout_{nome_slug}.pptx")

        return send_file(
            caminho_zip,
            mimetype="application/zip",
            as_attachment=True,
            download_name=f"arquivos_layout_{nome_slug}.zip",
        )

    except Exception as e:
        return jsonify({"erro": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
