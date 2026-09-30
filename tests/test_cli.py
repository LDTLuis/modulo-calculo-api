import json
import subprocess
import sys

import pytest

from damiq_calc.adapters.cli import main

REQUISICAO = {
    "versao_contrato": "1.0",
    "operacao": "processar_lote",
    "barragem": {"id": "joao-leite"},
    "configuracao": {
        "versao": 12,
        "sensores": {
            "PZ-01": {"tipo": "pressao", "faixa": {"min": 0, "max": 500, "unidade": "kPa"}, "frequencia_esperada_s": 3600}
        },
    },
    "opcoes": {"agora": "2026-09-30T12:00:00-03:00"},
    "medicoes": [
        {"sensor": "PZ-01", "tipo": "pressão", "timestamp": "2026-09-30T08:00:00-03:00", "valor": 132.4, "unidade": "kPa"},
        {"sensor": "PZ-01", "tipo": "pressão", "timestamp": "2026-09-30T11:00:00-03:00", "valor": 1.4, "unidade": "bar"},
        {"sensor": "PZ-01", "tipo": "pressão", "timestamp": "2026-09-30T11:30:00-03:00", "valor": "x", "unidade": "kPa"},
    ],
}


def executar(tmp_path, requisicao):
    entrada = tmp_path / "req.json"
    saida = tmp_path / "resp.json"
    texto = requisicao if isinstance(requisicao, str) else json.dumps(requisicao, ensure_ascii=False)
    entrada.write_text(texto, encoding="utf-8")
    codigo = main(["--entrada", str(entrada), "--saida", str(saida)])
    return codigo, json.loads(saida.read_text(encoding="utf-8"))


def test_processar_lote(tmp_path):
    codigo, resp = executar(tmp_path, REQUISICAO)
    assert codigo == 0
    assert resp["status"] == "OK"
    assert resp["versao_config"] == 12
    assert resp["resumo"] == {
        "recebidas": 3,
        "validas": 2,
        "rejeitadas": 1,
        "lacunas": 1,
        "alertas": 0,
        "historico": {"recebidas": 0, "validas": 0, "rejeitadas": 0},
    }
    assert resp["monitoramento"]["status_barragem"] == "OK"
    assert resp["medicoes"][1]["valor"] == pytest.approx(140.0)
    assert resp["rejeicoes"][0] == {
        "indice": 2,
        "codigo": "VALOR_INVALIDO",
        "mensagem": "Valor não numérico: 'x'",
    }
    assert resp["lacunas"][0]["duracao_s"] == 3 * 3600


def test_info(tmp_path):
    codigo, resp = executar(tmp_path, {"versao_contrato": "1.0", "operacao": "info"})
    assert codigo == 0
    assert "processar_lote" in resp["motor"]["operacoes"]


@pytest.mark.parametrize(
    ("requisicao", "codigo_erro"),
    [
        ("{nao é json", "JSON_INVALIDO"),
        ([], "CONTRATO_INVALIDO"),
        ({"operacao": "info"}, "VERSAO_INCOMPATIVEL"),
        ({"versao_contrato": "2.0", "operacao": "info"}, "VERSAO_INCOMPATIVEL"),
        ({"versao_contrato": "1.0", "operacao": "voar"}, "OPERACAO_DESCONHECIDA"),
        ({"versao_contrato": "1.0", "operacao": "processar_lote"}, "CONTRATO_INVALIDO"),
        (
            {"versao_contrato": "1.0", "operacao": "processar_lote", "medicoes": [],
             "configuracao": {"sensores": {}}},
            "CONTRATO_INVALIDO",
        ),
        (
            {"versao_contrato": "1.0", "operacao": "processar_lote", "medicoes": [],
             "opcoes": {"agora": "2026-09-30T12:00:00"}},
            "CONTRATO_INVALIDO",
        ),
    ],
)
def test_erros_de_entrada_retornam_1(tmp_path, requisicao, codigo_erro):
    codigo, resp = executar(tmp_path, requisicao)
    assert codigo == 1
    assert resp["status"] == "ERRO"
    assert resp["erros"][0]["codigo"] == codigo_erro


def test_erro_interno_retorna_2(tmp_path, monkeypatch, capsys):
    from damiq_calc.adapters import contrato

    def explode(_):
        raise RuntimeError("falha simulada")

    monkeypatch.setitem(contrato.OPERACOES, "info", explode)
    codigo, resp = executar(tmp_path, {"versao_contrato": "1.0", "operacao": "info"})
    assert codigo == 2
    assert resp["erros"][0]["codigo"] == "ERRO_INTERNO"
    assert "RuntimeError" in capsys.readouterr().err


def test_processo_via_stdin_stdout():
    """Simula o ProcessBuilder do Desktop: JSON UTF-8 no stdin, resposta no stdout."""
    proc = subprocess.run(
        [sys.executable, "-m", "damiq_calc"],
        input=json.dumps(REQUISICAO, ensure_ascii=False).encode("utf-8"),
        capture_output=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr.decode()
    resp = json.loads(proc.stdout.decode("utf-8"))
    assert resp["medicoes"][0]["unidade_original"] == "kPa"
    assert resp["rejeicoes"][0]["mensagem"] == "Valor não numérico: 'x'"


def test_calcular(tmp_path):
    codigo, resp = executar(
        tmp_path,
        {
            "versao_contrato": "1.0",
            "operacao": "calcular",
            "calculo": "hidrostatica.subpressao",
            "entradas": {"largura_base": 56, "pressao_montante": 182, "pressao_jusante": {"valor": 72, "unidade": "kPa"}},
        },
    )
    assert codigo == 0
    assert resp["calculo"]["id"] == "hidrostatica.subpressao"
    assert resp["resultados"][0]["valor"] == pytest.approx(7112.0)
    assert resp["resultados"][0]["status"] == "OK"
    assert resp["memoria"]["passos"][0]["substituicao"] == "U = 56 · (182 + 72) / 2 = 7112 kN/m"
    assert resp["entradas"]["comprimento"] == {"valor": None, "unidade": "m"}


def test_calcular_erros_por_campo(tmp_path):
    codigo, resp = executar(
        tmp_path,
        {"versao_contrato": "1.0", "operacao": "calcular", "calculo": "hidrostatica.subpressao", "entradas": {"largura_base": -5}},
    )
    assert codigo == 1
    assert {e["campo"] for e in resp["erros"]} == {"largura_base", "pressao_montante", "pressao_jusante"}


def test_calcular_desconhecido(tmp_path):
    codigo, resp = executar(tmp_path, {"versao_contrato": "1.0", "operacao": "calcular", "calculo": "x.y"})
    assert codigo == 1
    assert resp["erros"] == [{"codigo": "CALCULO_DESCONHECIDO", "mensagem": "Cálculo desconhecido: 'x.y'", "campo": None}]


def test_listar_calculos(tmp_path):
    codigo, resp = executar(tmp_path, {"versao_contrato": "1.0", "operacao": "listar_calculos", "modulo": "hidrostatica"})
    assert codigo == 0
    empuxo = next(c for c in resp["calculos"] if c["id"] == "hidrostatica.empuxo")
    assert [e["nome"] for e in empuxo["entradas"]] == ["altura_agua", "inclinacao_montante", "comprimento", "gama_w"]
