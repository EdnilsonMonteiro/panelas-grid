import io
import json
import logging
import os
import zipfile

from flask import Flask, after_this_request, jsonify, request, send_file
from flask_cors import CORS

from database.database import inicializar_banco, obter_conexao
from exportadores.pdf import ExportadorPDF
from exportadores.pptx import ExportadorPPTX
from modelos import PedidoCliente
from secoes import (
    SecaoItensFixos,
    SecaoMioloTorres,
    SecaoPanelasRedondasComGaps,
    SecaoTorresGulosas,
)

inicializar_banco()

app = Flask(__name__)
CORS(app)

REGISTRO_SECOES = {
    "SecaoTorresGulosas": SecaoTorresGulosas,
    "SecaoPanelasRedondasComGaps": SecaoPanelasRedondasComGaps,
    "SecaoMioloTorres": SecaoMioloTorres,
    "SecaoItensFixos": SecaoItensFixos,
}

DIRETORIO_ATUAL = os.path.dirname(os.path.abspath(__file__))


def carregar_catalogo_por_nome(nome_catalogo: str) -> list:
    """Busca o catálogo no banco SQLite. Caso não ache, tenta ler o arquivo físico como fallback."""
    try:
        conn = obter_conexao()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT conteudo_json FROM catalogos WHERE nome_catalogo = ?",
            (nome_catalogo,),
        )
        resultado = cursor.fetchone()
        conn.close()

        if resultado:
            return json.loads(resultado["conteudo_json"])
    except Exception as e:
        print(f"Erro ao acessar SQLite para catálogo: {e}")

    caminho_pasta = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "catalogos"
    )
    caminho_arquivo = os.path.join(caminho_pasta, f"{nome_catalogo}.json")

    if os.path.exists(caminho_arquivo):
        with open(caminho_arquivo, "r", encoding="utf-8") as f:
            print(
                f" > [Aviso] Catálogo '{nome_catalogo}' carregado via arquivo físico (Fallback)."
            )
            return json.load(f)

    return []


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
    """Retorna os nomes de todos os catálogos disponíveis gravados no banco de dados."""
    try:
        conn = obter_conexao()
        cursor = conn.cursor()

        cursor.execute("SELECT nome_catalogo FROM catalogos ORDER BY nome_catalogo ASC")
        linhas = cursor.fetchall()
        conn.close()

        nomes_catalogos = [linha["nome_catalogo"] for linha in linhas]

        if not nomes_catalogos:
            return jsonify(["catalogo_mestre", "catalogo_gaps", "catalogo_saladas"])

        return jsonify(nomes_catalogos)
    except Exception as e:
        return jsonify({"erro": str(e)}), 500


@app.route("/api/catalogos/<string:nome_catalogo>", methods=["GET"])
def obter_itens_catalogo(nome_catalogo):
    """Retorna os itens internos de um catálogo específico."""
    try:
        conn = obter_conexao()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT conteudo_json FROM catalogos WHERE nome_catalogo = ?",
            (nome_catalogo,),
        )
        linha = cursor.fetchone()
        conn.close()

        if linha:
            return jsonify(json.loads(linha["conteudo_json"])), 200
        return jsonify([]), 200
    except Exception as e:
        return jsonify({"erro": str(e)}), 500


@app.route("/api/catalogos/<string:nome_catalogo>", methods=["POST", "OPTIONS"])
def salvar_itens_catalogo(nome_catalogo):
    """Salva ou atualiza a lista de itens de um catálogo no SQLite."""
    if request.method == "OPTIONS":
        return jsonify({"status": "ok"}), 200

    try:
        itens = request.json  # Array de cubas vindas do front
        if not isinstance(itens, list):
            return jsonify(
                {"erro": "O corpo da requisição deve ser uma lista de itens"}
            ), 400

        conteudo_string = json.dumps(itens, ensure_ascii=False)

        conn = obter_conexao()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT OR REPLACE INTO catalogos (nome_catalogo, conteudo_json)
            VALUES (?, ?)
        """,
            (nome_catalogo.strip(), conteudo_string),
        )
        conn.commit()
        conn.close()

        return jsonify({"mensagem": "Catálogo salvo com sucesso!"}), 200
    except Exception as e:
        return jsonify({"erro": str(e)}), 500


@app.route("/api/catalogos/<string:nome_catalogo>", methods=["DELETE"])
def deletar_catalogo_inteiro(nome_catalogo):
    """Remove um catálogo inteiro do banco de dados."""
    try:
        conn = obter_conexao()
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM catalogos WHERE nome_catalogo = ?", (nome_catalogo,)
        )
        conn.commit()
        conn.close()
        return jsonify({"mensagem": f"Catálogo {nome_catalogo} removido."}), 200
    except Exception as e:
        return jsonify({"erro": str(e)}), 500


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
    arquivos_locais_para_limpar = []
    try:
        dados_recebidos = request.json
        if not dados_recebidos:
            return jsonify({"erro": "Payload JSON ausente ou inválido"}), 400

        nome_cliente_ui = dados_recebidos.get("nome_cliente", "Cliente Não Informado")
        if not nome_cliente_ui.strip():
            nome_cliente_ui = "Cliente Não Informado"

        pedido = PedidoCliente(nome_cliente=nome_cliente_ui)

        pedido_processado = construir_pipeline_desde_json(dados_recebidos, pedido)

        nome_slug = nome_cliente_ui.replace(" ", "_").lower()

        import unicodedata

        nome_slug = "".join(
            c
            for c in unicodedata.normalize("NFD", nome_slug)
            if unicodedata.category(c) != "Mn"
        )

        caminho_pdf = os.path.join(DIRETORIO_ATUAL, f"layout_{nome_slug}.pdf")
        caminho_pptx = os.path.join(DIRETORIO_ATUAL, f"layout_{nome_slug}.pptx")

        arquivos_locais_para_limpar.extend([caminho_pdf, caminho_pptx])

        ExportadorPDF.gerar_layout(pedido_processado, caminho_pdf)
        ExportadorPPTX.gerar_layout(pedido_processado, caminho_pptx)

        memoria_zip = io.BytesIO()

        with zipfile.ZipFile(memoria_zip, "w", zipfile.ZIP_DEFLATED) as zipf:
            if os.path.exists(caminho_pdf):
                zipf.write(caminho_pdf, arcname=f"layout_{nome_slug}.pdf")
            if os.path.exists(caminho_pptx):
                zipf.write(caminho_pptx, arcname=f"layout_{nome_slug}.pptx")

        memoria_zip.seek(0)

        for arquivo in arquivos_locais_para_limpar:
            try:
                if os.path.exists(arquivo):
                    os.remove(arquivo)
                    print(f" > Temporário removido do disco: {arquivo}")
            except Exception as error:
                print(f"Erro na remoção imediata de {arquivo}: {error}")

        # --- EVENTO DE LIMPEZA EM SEGUNDO PLANO ---
        @after_this_request
        def limpar_residuos_restantes(response):
            for arquivo in arquivos_locais_para_limpar:
                if os.path.exists(arquivo):
                    try:
                        os.remove(arquivo)
                    except OSError as e:
                        logging.error(f"Erro ao remover o arquivo {arquivo}: {e}")
            return response

        # ------------------------------------------

        return send_file(
            memoria_zip,
            mimetype="application/zip",
            as_attachment=True,
            download_name=f"arquivos_layout_{nome_slug}.zip",
        )

    except Exception as e:
        for arquivo in arquivos_locais_para_limpar:
            if os.path.exists(arquivo):
                try:
                    os.remove(arquivo)
                except OSError as e:
                    logging.error(f"Erro ao remover o arquivo {arquivo}: {e}")
        return jsonify({"erro": str(e)}), 500


@app.route("/api/templates", methods=["GET"])
def listar_templates():
    """Retorna todos os modelos de pipelines salvos para alimentar o dropdown da UI."""
    try:
        conn = obter_conexao()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, nome_template, pipeline_secoes FROM templates_pipeline"
        )
        linhas = cursor.fetchall()
        conn.close()

        lista_templates = []
        for linha in linhas:
            lista_templates.append(
                {
                    "id": str(linha["id"]),
                    "nome_template": linha["nome_template"],
                    "pipeline_secoes": json.loads(
                        linha["pipeline_secoes"]
                    ),  # Deserializa o JSON
                }
            )

        return jsonify(lista_templates)
    except Exception as e:
        return jsonify({"erro": str(e)}), 500


@app.route("/api/templates", methods=["POST", "OPTIONS"])
def salvar_template():
    """Grava um novo modelo configurado pela UI no banco."""
    if request.method == "OPTIONS":
        return jsonify({"status": "ok"}), 200

    try:
        dados = request.json
        if not dados or "nome_template" not in dados or "pipeline_secoes" not in dados:
            return jsonify({"erro": "Parâmetros obrigatórios ausentes"}), 400

        nome_template = dados["nome_template"].strip()
        pipeline_json_string = json.dumps(dados["pipeline_secoes"], ensure_ascii=False)

        conn = obter_conexao()
        cursor = conn.cursor()

        query = "INSERT OR REPLACE INTO templates_pipeline (nome_template, pipeline_secoes) VALUES (?, ?)"
        cursor.execute(query, (nome_template, pipeline_json_string))

        conn.commit()
        conn.close()

        return jsonify({"mensagem": "Modelo gravado com sucesso!"}), 201

    except Exception as e:
        print(f"❌ Erro interno ao salvar template: {e}")
        return jsonify({"erro": str(e)}), 500


@app.route("/api/templates/<int:id_template>", methods=["DELETE"])
def deletar_template(id_template):
    """Remove um modelo de pipeline do banco de dados."""
    try:
        conn = obter_conexao()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM templates_pipeline WHERE id = ?", (id_template,))
        conn.commit()
        conn.close()
        return jsonify({"mensagem": "Modelo deletado com sucesso!"}), 200
    except Exception as e:
        return jsonify({"erro": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
