"""JSON Schema do contrato: atualizado, válido e coerente com o que o motor aceita e devolve."""

from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from damiq_calc.adapters.contrato import processar
from damiq_calc.adapters.esquemas import ESQUEMAS, serializar

PASTA = Path(__file__).resolve().parents[1] / "docs" / "schemas"
ESQUEMAS_GERADOS = {nome: construir() for nome, construir in ESQUEMAS.items()}
REGISTRO = Registry().with_resources((e["$id"], Resource.from_contents(e)) for e in ESQUEMAS_GERADOS.values())


def validador(nome):
    return Draft202012Validator(ESQUEMAS_GERADOS[nome], registry=REGISTRO)


def erros(nome, instancia):
    return sorted(e.message for e in validador(nome).iter_errors(instancia))


@pytest.mark.parametrize("nome", list(ESQUEMAS))
def test_arquivos_em_docs_estao_atualizados(nome):
    """Falhou? Rode `python -m damiq_calc.adapters.esquemas` e faça commit de docs/schemas/."""
    assert (PASTA / nome).read_text(encoding="utf-8") == serializar(ESQUEMAS_GERADOS[nome])


@pytest.mark.parametrize("nome", list(ESQUEMAS))
def test_esquemas_sao_validos(nome):
    Draft202012Validator.check_schema(ESQUEMAS_GERADOS[nome])


CONFIGURACAO = {
    "versao": 12,
    "fuso_padrao": "-03:00",
    "medicoes": {"tolerancia_futuro_s": 300, "fator_tolerancia_lacuna": 1.5},
    "padroes_por_tipo": {"pressao": {"faixa": {"min": 0, "max": 10, "unidade": "bar"}, "frequencia_esperada_s": 604800}},
    "sensores": {
        "PZ-01": {
            "tipo": "pressao",
            "faixa": {"min": 0, "max": 500, "unidade": "kPa"},
            "limites_alerta": {"unidade": "mca", "acima": {"aviso": 18, "alerta": 22, "critico": 26}},
            "cota_instalacao_m": 712.5,
        },
        "RN-01": {
            "tipo": "nivel",
            "limites_alerta": {"abaixo": {"aviso": 745, "critico": 740}},
            "taxa_variacao": {"unidade": "cm", "intervalo_s": 86400, "direcao": "descida", "aviso": 20, "alerta": 50},
        },
    },
    "monitoramento": {"anomalia": {"ativo": True, "janela_leituras": 24}, "sensor_travado": {"ativo": False}},
    "limites_calculo": {"fs_min_piping": 2.0, "fs_min_talude": 1.5},
}


def req(operacao, **campos):
    return {"versao_contrato": "1.0", "operacao": operacao, **campos}


REQUISICOES_VALIDAS = [
    req("info"),
    req("listar_calculos", modulo="percolacao"),
    req("validar_configuracao", configuracao=CONFIGURACAO),
    req(
        "processar_lote",
        configuracao=CONFIGURACAO,
        opcoes={"agora": "2026-09-30T12:00:00-03:00"},
        historico=[{"sensor": "PZ-01", "tipo": "pressao", "timestamp": "2026-09-01T08:00:00", "valor": 150, "unidade": "kPa"}],
        medicoes=[
            {"sensor": "PZ-01", "tipo": "pressao", "timestamp": "2026-09-08T08:00:00", "valor": 2.3, "unidade": "bar"},
            {"sensor": "RN-01", "tipo": "nivel", "timestamp": "2026-09-08T08:00:00", "valor": "744,5", "unidade": "m"},
        ],
    ),
    req("calcular", calculo="percolacao.piping", configuracao=CONFIGURACAO,
        entradas={"perda_carga_total": 15.4, "n_d": 14, "comprimento_celula": {"valor": 300, "unidade": "cm"}, "gama_sat": 18, "gama_w": 10}),
    req("calcular", calculo="estabilidade.talude_bishop",
        entradas={"fatias": [{"largura": 2, "peso": 100, "alfa": {"valor": 0.35, "unidade": "rad"}, "coesao": 10, "phi": 28}]}),
    req("calcular", calculo="hidrologia.periodo_retorno", entradas={"risco": {"valor": 1, "unidade": "%"}, "vida_util": 1000}),
]


@pytest.mark.parametrize("requisicao", REQUISICOES_VALIDAS, ids=lambda r: r.get("calculo", r["operacao"]))
def test_requisicoes_validas_passam_no_schema_e_no_motor(requisicao):
    assert erros("requisicao.schema.json", requisicao) == []
    resposta = processar(requisicao)
    assert resposta["status"] == "OK"
    assert erros("resposta.schema.json", resposta) == []


def test_resposta_de_lote_com_alertas_e_graficos_segue_o_schema(tmp_path):
    requisicao = dict(REQUISICOES_VALIDAS[3], opcoes={"agora": "2026-09-30T12:00:00-03:00", "graficos": {"diretorio": str(tmp_path)}})
    assert erros("requisicao.schema.json", requisicao) == []
    resposta = processar(requisicao)
    assert resposta["alertas"], "o exemplo deveria gerar alertas"
    assert resposta["graficos"]
    assert erros("resposta.schema.json", resposta) == []


@pytest.mark.parametrize(
    ("requisicao", "trecho"),
    [
        (req("calcular", calculo="percolacao.piping", entradas={"perda_carga_total": 15.4}), "is a required property"),
        (req("calcular", calculo="percolacao.pipin", entradas={}), "is not one of"),
        (req("calcular", calculo="hidrostatica.pressao", entradas={"profundidade": -1}), "is not valid under any of the given schemas"),
        (req("calcular", calculo="hidrostatica.pressao", entradas={"profundidade": 1, "altura": 2}), "Additional properties"),
        (req("processar_lote"), "'medicoes' is a required property"),
        (req("validar_configuracao"), "'configuracao' is a required property"),
        (req("validar_configuracao", configuracao={"versao": 1, "sensores": {"PZ-01": {"tipo": "pressao", "limite_alerta": {}}}}), "Additional properties"),
        (req("validar_configuracao", configuracao={"versao": 1, "limites_calculo": {"fs_min_pipping": 2}}), "Additional properties"),
        (req("validar_configuracao", configuracao={"sensores": {}}), "'versao' is a required property"),
        (req("voar"), "is not one of"),
        ({"operacao": "info"}, "'versao_contrato' is a required property"),
    ],
)
def test_schema_recusa_requisicoes_erradas(requisicao, trecho):
    mensagens = erros("requisicao.schema.json", requisicao)
    assert any(trecho in m for m in mensagens), mensagens


def test_resposta_de_erro_segue_o_schema():
    from damiq_calc.adapters.contrato import resposta_erro

    resposta = resposta_erro("calcular", "ENTRADAS_INVALIDAS", "x", [{"campo": "n_d", "codigo": "CAMPO_AUSENTE", "mensagem": "campo obrigatório"}])
    assert erros("resposta.schema.json", resposta) == []


def test_schema_de_calculos_cobre_o_catalogo():
    from damiq_calc.catalogo import REGISTRO

    assert set(ESQUEMAS_GERADOS["calculos.schema.json"]["$defs"]) == set(REGISTRO)
    limites = ESQUEMAS_GERADOS["configuracao.schema.json"]["properties"]["limites_calculo"]["properties"]
    assert limites["fs_min_piping"]["default"] == 1.5
    assert limites["fs_min_talude"]["x-calculos"] == ["estabilidade.talude_fellenius", "estabilidade.talude_bishop"]
