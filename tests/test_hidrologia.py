"""M6 – casos de referência da apostila BCST (Notas 01–06)."""

import pytest

from damiq_calc.catalogo import REGISTRO, executar
from damiq_calc.core.calculo import ErroEntradas
from damiq_calc.core.resultado import Severidade


def por_nome(ex):
    return {r.calculo.rsplit(".", 1)[-1]: r for r in ex.resultados}


# AP slides 99–101: áreas das curvas 100–103; a cota 99,5 marca o fundo (área 0)
CURVAS_AP = [
    {"cota": 99.5, "area": 0},
    {"cota": 100, "area": 980},
    {"cota": 101, "area": 1680},
    {"cota": 102, "area": 2048},
    {"cota": 103, "area": 2720},
]


def test_volume_por_curvas_de_nivel_exemplo_da_apostila():
    """AP: 245 + 1330 + 1864 + 2384 = 5823 m³."""
    ex = executar("hidrologia.curva_cota_volume", {"pontos": CURVAS_AP})
    assert por_nome(ex)["volume_total"].valor == pytest.approx(5823.0)
    assert [linha[4] for linha in ex.memoria.tabelas[0]["linhas"]] == pytest.approx([0, 245, 1330, 1864, 2384])


def test_pontos_fora_de_ordem_sao_ordenados():
    ex = executar("hidrologia.curva_cota_volume", {"pontos": list(reversed(CURVAS_AP))})
    assert por_nome(ex)["volume_total"].valor == pytest.approx(5823.0)


def test_consulta_de_cota_intermediaria():
    ex = executar("hidrologia.curva_cota_volume", {"pontos": CURVAS_AP, "cota_consulta": 102.5})
    r = por_nome(ex)
    assert r["area_consulta"].valor == pytest.approx(2384.0)
    assert r["volume_consulta"].valor == pytest.approx(245 + 1330 + 1864 + (2048 + 2384) / 2 * 0.5)


@pytest.mark.parametrize("cota", [99.5, 103])
def test_consulta_nas_extremidades(cota):
    ex = executar("hidrologia.curva_cota_volume", {"pontos": CURVAS_AP, "cota_consulta": cota})
    assert por_nome(ex)["volume_consulta"].valor == pytest.approx(0 if cota == 99.5 else 5823)


def test_consulta_fora_da_curva_e_cota_repetida():
    with pytest.raises(ErroEntradas) as exc:
        executar("hidrologia.curva_cota_volume", {"pontos": CURVAS_AP, "cota_consulta": 104})
    assert exc.value.erros[0]["campo"] == "cota_consulta"
    with pytest.raises(ErroEntradas):
        executar("hidrologia.curva_cota_volume", {"pontos": CURVAS_AP + [{"cota": 103, "area": 3000}]})


def test_area_em_hectares():
    pontos = [{"cota": 0, "area": 0}, {"cota": 2, "area": {"valor": 1, "unidade": "ha"}}]
    assert por_nome(executar("hidrologia.curva_cota_volume", {"pontos": pontos}))["volume_total"].valor == pytest.approx(10000)


def test_volume_por_secoes():
    ex = executar("hidrologia.volume_secoes", {"secoes": [{"area": 12, "distancia": 10}, {"area": 20, "distancia": 15}]})
    assert por_nome(ex)["volume"].valor == pytest.approx(420)


def test_vazao_medida_tambor():
    """AP: Q = Volume / Tempo médio, com três repetições."""
    ex = executar("hidrologia.vazao_medida", {"volume": {"valor": 200, "unidade": "L"}, "tempos": [{"tempo": 40}, {"tempo": 42}, {"tempo": 38}]})
    r = por_nome(ex)
    assert r["tempo_medio"].valor == pytest.approx(40)
    assert r["vazao"].valor == pytest.approx(0.005)
    assert ex.memoria.premissas == []


def test_vazao_medida_com_menos_de_tres_repeticoes():
    ex = executar("hidrologia.vazao_medida", {"volume": 0.2, "tempos": [{"tempo": {"valor": 1, "unidade": "min"}}]})
    assert por_nome(ex)["vazao"].valor == pytest.approx(0.2 / 60)
    assert "a apostila recomenda três" in ex.memoria.premissas[0]


def test_metodo_racional():
    ex = executar("hidrologia.metodo_racional", {"coeficiente_escoamento": 0.5, "intensidade": 100, "area": 72})
    q = por_nome(ex)["vazao"]
    assert q.valor == pytest.approx(10.0)
    assert q.severidade is Severidade.OK


def test_metodo_racional_fora_do_dominio():
    ex = executar("hidrologia.metodo_racional", {"coeficiente_escoamento": 0.5, "intensidade": 100, "area": {"valor": 3, "unidade": "km2"}})
    q = por_nome(ex)["vazao"]
    assert q.valor == pytest.approx(0.5 * 100 * 300 / 360)
    assert (q.severidade, q.limite) == (Severidade.AVISO, 200)


@pytest.mark.parametrize(
    ("risco", "esperado"),
    [
        (0.01, 99499.6),  # AP slide 232: R = 1%, n = 1000 → Tr ≈ 99.500 anos
        ({"valor": 20, "unidade": "%"}, 4481.92),  # AP slide 233: R = 20% → Tr ≈ 4.480 anos
    ],
)
def test_periodo_retorno_exemplos_da_apostila(risco, esperado):
    tr = por_nome(executar("hidrologia.periodo_retorno", {"risco": risco, "vida_util": 1000}))["tr"]
    assert tr.valor == pytest.approx(esperado, rel=1e-5)


def test_periodo_retorno_risco_invalido():
    with pytest.raises(ErroEntradas):
        executar("hidrologia.periodo_retorno", {"risco": 1, "vida_util": 50})


@pytest.mark.parametrize(
    ("consumo", "rotulo", "severidade"),
    [
        (0.4, "Normal", Severidade.OK),
        (0.5, "Alerta", Severidade.AVISO),
        (0.9, "Moderadamente crítico", Severidade.ALERTA),
        (1.0, "Moderadamente crítico", Severidade.ALERTA),
        (1.2, "Altamente crítico", Severidade.CRITICO),
    ],
)
def test_indice_de_demanda(consumo, rotulo, severidade):
    # Qref = 0,01 m³/s/km² · 100 km² = 1 m³/s
    ex = executar("hidrologia.indice_demanda", {"vazao_especifica": 0.01, "area_drenagem": 100, "vazao_consumo": consumo})
    idx = por_nome(ex)["indice"]
    assert idx.valor == pytest.approx(consumo * 100)
    assert (idx.rotulo, idx.severidade) == (rotulo, severidade)


def test_indice_de_demanda_com_l_s_km2():
    ex = executar("hidrologia.indice_demanda", {"vazao_especifica": {"valor": 10, "unidade": "L/s/km2"}, "area_drenagem": 100, "vazao_consumo": {"valor": 400, "unidade": "L/s"}})
    assert por_nome(ex)["indice"].valor == pytest.approx(40)


@pytest.mark.parametrize(("capacidade", "severidade"), [(12, Severidade.OK), (10, Severidade.OK), (8, Severidade.CRITICO)])
def test_extravasor(capacidade, severidade):
    ex = executar("hidrologia.extravasor", {"vazao_projeto": 10, "capacidade": capacidade})
    assert por_nome(ex)["razao"].severidade is severidade


def test_catalogo_m6():
    assert {k for k in REGISTRO if k.startswith("hidrologia.")} == {
        "hidrologia.curva_cota_volume",
        "hidrologia.volume_secoes",
        "hidrologia.vazao_medida",
        "hidrologia.metodo_racional",
        "hidrologia.periodo_retorno",
        "hidrologia.indice_demanda",
        "hidrologia.extravasor",
    }
    risco = next(e for e in REGISTRO["hidrologia.periodo_retorno"].para_dict()["entradas"] if e["nome"] == "risco")
    assert risco["unidades_aceitas"] == ["-", "%"]
