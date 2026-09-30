"""M3 – casos de referência tirados dos exercícios resolvidos da apostila BCST (γw = 10 kN/m³)."""

import pytest

from damiq_calc.catalogo import REGISTRO, executar
from damiq_calc.core.calculo import ErroEntradas

GW10 = {"gama_w": 10}


def valores(execucao):
    return {r.calculo.rsplit(".", 1)[-1]: r.valor for r in execucao.resultados}


def test_pressao_hidrostatica():
    ex = executar("hidrostatica.pressao", {"profundidade": 13.8, **GW10})
    [r] = ex.resultados
    assert (r.valor, r.unidade) == (pytest.approx(138.0), "kPa")


def test_gama_w_padrao_vira_premissa():
    ex = executar("hidrostatica.pressao", {"profundidade": 10})
    assert ex.resultados[0].valor == pytest.approx(98.1)
    assert ex.memoria.premissas == ["gama_w = 9,81 kN/m3 (padrão)"]
    assert ex.resultados[0].premissas == ("gama_w = 9,81 kN/m3 (padrão)",)


@pytest.mark.parametrize(
    ("quedas", "carga_total", "carga_piezometrica", "pressao"),
    [
        # AP, Exercício 1 – ponto P: Ht = 40 + 15,4 − 2·1,1 = 53,2; Hp = 18,2 m; u = 182 kPa
        (2, 53.2, 18.2, 182.0),
        # AP, slide 540 – ponto A: Ht = 55,4 − 1,1·6 = 48,8; hw = 13,8 m; u = 138 kPa
        (6, 48.8, 13.8, 138.0),
        # AP, Exercício 1 – ponto Q: Ht = 42,2; Hp = 7,2 m; u = 72 kPa
        (12, 42.2, 7.2, 72.0),
    ],
)
def test_carga_rede_fluxo_exemplos_da_apostila(quedas, carga_total, carga_piezometrica, pressao):
    ex = executar(
        "hidrostatica.carga_rede_fluxo",
        {"cota_na_montante": 55.4, "perda_carga_total": 15.4, "n_d": 14, "quedas_percorridas": quedas, "cota_ponto": 35, **GW10},
    )
    v = valores(ex)
    assert v["delta_h"] == pytest.approx(1.1)
    assert v["carga_total"] == pytest.approx(carga_total)
    assert v["carga_piezometrica"] == pytest.approx(carga_piezometrica)
    assert v["pressao"] == pytest.approx(pressao)


def test_memoria_de_calculo_rede_fluxo():
    ex = executar(
        "hidrostatica.carga_rede_fluxo",
        {"cota_na_montante": 55.4, "perda_carga_total": 15.4, "n_d": 14, "quedas_percorridas": 2, "cota_ponto": 35, **GW10},
    )
    assert [p.substituicao for p in ex.memoria.passos] == [
        "Δh = 15,4 / 14 = 1,1 m",
        "Ht = 55,4 − 2 · 1,1 = 53,2 m",
        "Ha = cota do ponto = 35 m",
        "Hp = 53,2 − 35 = 18,2 m",
        "u = 10 · 18,2 = 182 kPa",
    ]


def test_quedas_nao_podem_exceder_nd():
    with pytest.raises(ErroEntradas) as exc:
        executar(
            "hidrostatica.carga_rede_fluxo",
            {"cota_na_montante": 55.4, "perda_carga_total": 15.4, "n_d": 14, "quedas_percorridas": 15, "cota_ponto": 35},
        )
    assert exc.value.erros[0]["campo"] == "quedas_percorridas"


def test_subpressao_exemplo_da_apostila():
    """AP, Exercício 1: F = 56 · (182 + 72) / 2 = 7.112 kN/m."""
    ex = executar("hidrostatica.subpressao", {"largura_base": 56, "pressao_montante": 182, "pressao_jusante": 72})
    v = valores(ex)
    assert v["por_metro"] == pytest.approx(7112.0)
    assert v["braco"] == pytest.approx(56 * (182 + 2 * 72) / (3 * 254))
    assert "total" not in v


def test_subpressao_com_comprimento_e_pressao_em_mca():
    ex = executar(
        "hidrostatica.subpressao",
        {"largura_base": 10, "pressao_montante": {"valor": 2, "unidade": "mca"}, "pressao_jusante": 0, "comprimento": 100},
    )
    v = valores(ex)
    assert v["por_metro"] == pytest.approx(10 * 19.62 / 2)
    assert v["braco"] == pytest.approx(10 / 3)  # diagrama triangular
    assert v["total"] == pytest.approx(10 * 19.62 / 2 * 100)


def test_empuxo_paramento_vertical():
    """AP: E = γ · H² · L / 2."""
    ex = executar("hidrostatica.empuxo", {"altura_agua": 10, "comprimento": 50, **GW10})
    v = valores(ex)
    assert v["horizontal"] == pytest.approx(500.0)
    assert v["braco_horizontal"] == pytest.approx(10 / 3)
    assert v["total"] == pytest.approx(25000.0)
    assert "vertical" not in v


def test_empuxo_paramento_inclinado():
    ex = executar("hidrostatica.empuxo", {"altura_agua": 6, "inclinacao_montante": 3, **GW10})
    v = valores(ex)
    assert v["horizontal"] == pytest.approx(180.0)
    assert v["vertical"] == pytest.approx(540.0)  # 10 · 3 · 36 / 2
    assert v["braco_vertical"] == pytest.approx(6.0)
    assert v["resultante"] == pytest.approx((180**2 + 540**2) ** 0.5)


def test_piezometro():
    ex = executar("hidrostatica.piezometro", {"pressao": {"valor": 1.962, "unidade": "bar"}, "cota_instalacao": 712.0})
    v = valores(ex)
    assert v["carga"] == pytest.approx(20.0)
    assert v["cota"] == pytest.approx(732.0)


@pytest.mark.parametrize(
    ("entradas", "campo", "codigo"),
    [
        ({}, "profundidade", "CAMPO_AUSENTE"),
        ({"profundidade": -1}, "profundidade", "FORA_DO_INTERVALO"),
        ({"profundidade": "10"}, "profundidade", "VALOR_INVALIDO"),
        ({"profundidade": {"valor": 1, "unidade": "kPa"}}, "profundidade", "UNIDADE_INCOMPATIVEL"),
        ({"profundidade": {"valor": 1, "unidade": "pés"}}, "profundidade", "UNIDADE_DESCONHECIDA"),
        ({"profundidade": 1, "gama_w": 0}, "gama_w", "FORA_DO_INTERVALO"),
        ({"profundidade": 1, "altura": 2}, "altura", "CAMPO_DESCONHECIDO"),
    ],
)
def test_erros_por_campo(entradas, campo, codigo):
    with pytest.raises(ErroEntradas) as exc:
        executar("hidrostatica.pressao", entradas)
    assert (exc.value.erros[0]["campo"], exc.value.erros[0]["codigo"]) == (campo, codigo)


def test_erros_de_varios_campos_sao_reunidos():
    with pytest.raises(ErroEntradas) as exc:
        executar("hidrostatica.subpressao", {"largura_base": 0, "pressao_montante": -1})
    assert {e["campo"] for e in exc.value.erros} == {"largura_base", "pressao_montante", "pressao_jusante"}


def test_inteiro():
    with pytest.raises(ErroEntradas):
        executar(
            "hidrostatica.carga_rede_fluxo",
            {"cota_na_montante": 55.4, "perda_carga_total": 15.4, "n_d": 14.5, "quedas_percorridas": 2, "cota_ponto": 35},
        )


def test_catalogo_m3():
    assert {k for k in REGISTRO if k.startswith("hidrostatica.")} == {
        "hidrostatica.pressao",
        "hidrostatica.piezometro",
        "hidrostatica.carga_rede_fluxo",
        "hidrostatica.empuxo",
        "hidrostatica.subpressao",
    }
    descricao = REGISTRO["hidrostatica.pressao"].para_dict()
    gama = next(e for e in descricao["entradas"] if e["nome"] == "gama_w")
    assert gama["obrigatoria"] is False and gama["padrao"] == 9.81
    prof = next(e for e in descricao["entradas"] if e["nome"] == "profundidade")
    assert "cm" in prof["unidades_aceitas"]
