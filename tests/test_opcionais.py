"""M11 – cálculos opcionais [LIT]."""

import pytest

from damiq_calc.catalogo import REGISTRO, executar
from damiq_calc.core.resultado import Severidade


def valor(ex, nome):
    return next(r for r in ex.resultados if r.calculo.endswith("." + nome))


def test_vertedor_retangular_francis():
    ex = executar("opcionais.vertedor_retangular", {"largura": 2, "carga": 0.25})
    assert valor(ex, "vazao").valor == pytest.approx(1.838 * 2 * 0.25**1.5)
    assert "coeficiente = 1,838 (padrão)" in ex.memoria.premissas
    assert any(p.startswith("Cálculo da literatura técnica") for p in ex.memoria.premissas)


def test_vertedor_triangular_thomson():
    ex = executar("opcionais.vertedor_triangular", {"carga": {"valor": 10, "unidade": "cm"}})
    assert valor(ex, "vazao").valor == pytest.approx(1.4 * 0.1**2.5)  # ≈ 4,43 L/s


def test_evapotranspiracao_exemplo_18_da_fao56():
    """FAO-56, Exemplo 18 (dados diários): ET0 ≈ 3,9 mm/dia."""
    ex = executar(
        "opcionais.evapotranspiracao_fao56",
        {
            "saldo_radiacao": 13.28,
            "temperatura": 16.9,
            "vento_2m": 2.078,
            "pressao_saturacao": 1.997,
            "pressao_real": 1.409,
            "declividade_curva": 0.122,
            "constante_psicrometrica": 0.0666,
        },
    )
    assert valor(ex, "et0").valor == pytest.approx(3.9, abs=0.05)


def test_balanco_hidrico():
    # Qin 2, Qout 1,5, perdas 0,05, E = 5 mm/dia em 1 km² → Qevap ≈ 0,0579 m³/s; 10 dias
    ex = executar(
        "opcionais.balanco_hidrico",
        {
            "vazao_afluente": 2,
            "vazao_efluente": 1.5,
            "vazao_perdas": 0.05,
            "evaporacao": 5,
            "area_espelho": {"valor": 1, "unidade": "km2"},
            "intervalo": 10,
            "volume_inicial": 1e6,
        },
    )
    qevap = 5 * 1e6 / 86_400_000
    dv = (2 - 1.5 - qevap - 0.05) * 10 * 86400
    assert valor(ex, "vazao_evaporacao").valor == pytest.approx(qevap)
    assert valor(ex, "variacao_volume").valor == pytest.approx(dv)
    assert valor(ex, "volume_final").valor == pytest.approx(1e6 + dv)


def test_balanco_que_esvazia_o_reservatorio():
    ex = executar("opcionais.balanco_hidrico", {"vazao_afluente": 0, "vazao_efluente": 1, "intervalo": 30, "volume_inicial": 1e5})
    vf = valor(ex, "volume_final")
    assert (vf.valor, vf.severidade) == (0.0, Severidade.ALERTA)


def test_pico_ruptura_froehlich():
    ex = executar("opcionais.pico_ruptura_froehlich", {"volume_reservatorio": {"valor": 3, "unidade": "hm3"}, "altura_agua_brecha": 15})
    assert valor(ex, "vazao_pico").valor == pytest.approx(0.607 * 3e6**0.295 * 15**1.24)
    assert any("HEC-RAS" in p for p in ex.memoria.premissas)


def test_catalogo_m11():
    ids = {k for k in REGISTRO if k.startswith("opcionais.")}
    assert ids == {
        "opcionais.vertedor_retangular",
        "opcionais.vertedor_triangular",
        "opcionais.evapotranspiracao_fao56",
        "opcionais.balanco_hidrico",
        "opcionais.pico_ruptura_froehlich",
    }
    assert all(REGISTRO[i].fonte.startswith("[LIT]") for i in ids)
