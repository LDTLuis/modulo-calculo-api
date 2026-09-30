"""M8 – classificação regulatória (Lei 12.334/2010, Res. CNRH 143/2012, IN SEMAD 01/2020)."""

import pytest

from damiq_calc.catalogo import REGISTRO, executar
from damiq_calc.core.calculo import ErroEntradas
from damiq_calc.core.resultado import Severidade


def por_nome(ex):
    return {r.calculo.rsplit(".", 1)[-1]: r for r in ex.resultados}


@pytest.mark.parametrize(
    ("entradas", "enquadrada", "grupo"),
    [
        ({"altura_macico": 16, "capacidade": 5e5}, "SIM", "Grupo 1"),
        ({"altura_macico": 8, "capacidade": {"valor": 3.2, "unidade": "hm3"}}, "SIM", "Grupo 1"),
        ({"altura_macico": 8, "capacidade": 1.5e6}, "NÃO", "Grupo 2"),
        ({"altura_macico": 3, "capacidade": 2e5}, "NÃO", "Grupo 3"),
        ({"altura_macico": 3, "capacidade": 2e5, "residuos_perigosos": 1}, "SIM", "Grupo 3"),
        ({"altura_macico": 3, "capacidade": 2e5, "dpa": 12}, "SIM", "Grupo 3"),
        ({"altura_macico": 3, "capacidade": 2e5, "dpa": 8}, "NÃO", "Grupo 3"),
    ],
)
def test_enquadramento_pnsb(entradas, enquadrada, grupo):
    r = por_nome(executar("classificacao.enquadramento_pnsb", entradas))
    assert r["enquadrada"].rotulo == enquadrada
    assert r["grupo_semad"].rotulo == grupo


def test_enquadramento_sem_dpa_registra_premissa():
    ex = executar("classificacao.enquadramento_pnsb", {"altura_macico": 3, "capacidade": 2e5})
    assert any("DPA não informado" in p for p in ex.memoria.premissas)


@pytest.mark.parametrize(
    ("cri", "dpa", "risco", "cat_dpa", "classe", "anos"),
    [
        # linha ALTO da matriz: A B C
        (65, 18, "ALTO", "ALTO", "A", 5),
        (65, 12, "ALTO", "MÉDIO", "B", 7),
        (65, 5, "ALTO", "BAIXO", "C", 10),
        # linha MÉDIO: A C D
        (40, 18, "MÉDIO", "ALTO", "A", 5),
        (40, 12, "MÉDIO", "MÉDIO", "C", 10),
        (40, 5, "MÉDIO", "BAIXO", "D", 12),
        # linha BAIXO: A D D
        (30, 18, "BAIXO", "ALTO", "A", 5),
        (30, 12, "BAIXO", "MÉDIO", "D", 12),
        (30, 5, "BAIXO", "BAIXO", "D", 12),
    ],
)
def test_matriz_de_classificacao(cri, dpa, risco, cat_dpa, classe, anos):
    ex = executar("classificacao.risco", {"ct": cri - 10, "ec": 5, "ps": 5, "dpa": dpa})
    r = por_nome(ex)
    assert r["cri"].valor == cri
    assert (r["cri"].rotulo, r["dpa"].rotulo, r["classe"].rotulo) == (risco, cat_dpa, classe)
    assert r["periodicidade_rpsb"].valor == anos


@pytest.mark.parametrize(("cri", "rotulo"), [(60, "ALTO"), (59, "MÉDIO"), (36, "MÉDIO"), (35, "BAIXO")])
def test_faixas_de_cri(cri, rotulo):
    assert por_nome(executar("classificacao.risco", {"ct": cri, "ec": 0, "ps": 0, "dpa": 0}))["cri"].rotulo == rotulo


@pytest.mark.parametrize(("dpa", "rotulo"), [(16, "ALTO"), (15, "MÉDIO"), (11, "MÉDIO"), (10, "BAIXO")])
def test_faixas_de_dpa(dpa, rotulo):
    assert por_nome(executar("classificacao.risco", {"ct": 0, "ec": 0, "ps": 0, "dpa": dpa}))["dpa"].rotulo == rotulo


def test_item_de_ec_com_10_torna_risco_alto():
    """AP: pontuação 10 em qualquer coluna de EC implica categoria de risco ALTA."""
    ex = executar("classificacao.risco", {"ct": 5, "ec": 12, "ps": 3, "ec_item_maximo": 10, "dpa": 5})
    cri = por_nome(ex)["cri"]
    assert (cri.valor, cri.rotulo, cri.severidade) == (20, "ALTO", Severidade.CRITICO)
    assert "intervenção imediata" in ex.memoria.conclusoes[0]
    assert por_nome(ex)["classe"].rotulo == "C"


def test_faixas_configuraveis_na_central():
    ex = executar("classificacao.risco", {"ct": 30, "ec": 10, "ps": 5, "dpa": 5}, {"cri_limite_medio": 50})
    assert por_nome(ex)["cri"].rotulo == "BAIXO"
    assert "cri_limite_medio = 50 (configuração da Central)" in ex.memoria.premissas


def test_ec_item_maior_que_total():
    with pytest.raises(ErroEntradas):
        executar("classificacao.risco", {"ct": 5, "ec": 4, "ps": 3, "ec_item_maximo": 10, "dpa": 5})


def test_catalogo_m8():
    assert {k for k in REGISTRO if k.startswith("classificacao.")} == {"classificacao.enquadramento_pnsb", "classificacao.risco"}
