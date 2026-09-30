"""M7 – casos de referência da apostila BCST, Nota 02."""

import pytest

from damiq_calc.catalogo import REGISTRO, executar
from damiq_calc.core.resultado import Severidade


def por_nome(ex):
    return {r.calculo.rsplit(".", 1)[-1]: r for r in ex.resultados}


# AP slide 113: taludes 3:1 e 2:1, crista de 3 m; 11 trapézios, total 1.336,625 m³
TRECHOS_AP = [
    {"altura": 5.5, "comprimento": 3},
    {"altura": 5, "comprimento": 3},
    {"altura": 5, "comprimento": 3},
    {"altura": 4, "comprimento": 3},
    {"altura": 4, "comprimento": 3},
    {"altura": 3, "comprimento": 3},
    {"altura": 3, "comprimento": 2.5},
    {"altura": 2, "comprimento": 2.5},
    {"altura": 2, "comprimento": 3},
    {"altura": 1, "comprimento": 2},
    {"altura": 1, "comprimento": 2},
]


def test_volume_de_terra_exemplo_da_apostila():
    ex = executar("geometria.volume_terra", {"largura_crista": 3, "trechos": TRECHOS_AP})
    assert por_nome(ex)["volume"].valor == pytest.approx(1336.625)
    # AP: V = (5h² + 6h)·L/2 para crista de 3 m e taludes 3:1 / 2:1
    assert [linha[3] for linha in ex.memoria.tabelas[0]["linhas"]] == pytest.approx(
        [276.375, 232.5, 232.5, 156, 156, 94.5, 78.75, 40, 48, 11, 11]
    )
    assert "talude_montante = 3 (padrão)" in ex.memoria.premissas


@pytest.mark.parametrize(("volume_agua", "severidade"), [(5823, Severidade.OK), (3000, Severidade.AVISO)])
def test_relacao_agua_terra(volume_agua, severidade):
    """AP: a relação volume de água : volume de terra deve ser no mínimo 3:1."""
    ex = executar("geometria.volume_terra", {"largura_crista": 3, "trechos": TRECHOS_AP, "volume_agua": volume_agua})
    r = por_nome(ex)["relacao_agua_terra"]
    assert r.valor == pytest.approx(volume_agua / 1336.625)
    assert (r.severidade, r.limite) == (severidade, 3.0)


def test_secao_do_macico_recomendada():
    ex = executar("geometria.secao_macico", {"altura": 5, "largura_crista": 3})
    r = por_nome(ex)
    assert r["largura_base"].valor == pytest.approx(3 + 5 * 5)
    assert r["area"].valor == pytest.approx((5 * 25 + 6 * 5) / 2)
    assert all(x.severidade is Severidade.OK for x in ex.resultados)
    assert len(ex.memoria.conclusoes) == 3


def test_secao_fora_da_recomendacao_gera_aviso():
    ex = executar("geometria.secao_macico", {"altura": 5, "largura_crista": 2, "talude_montante": 2.5, "talude_jusante": 1.5})
    r = por_nome(ex)
    assert (r["crista"].severidade, r["crista"].limite) == (Severidade.AVISO, 2.5)
    assert r["talude_montante"].severidade is Severidade.AVISO
    assert r["talude_jusante"].severidade is Severidade.AVISO
    assert "verificar in loco" in ex.memoria.conclusoes[0]


def test_limites_da_central_na_geometria():
    ex = executar("geometria.secao_macico", {"altura": 5, "largura_crista": 3}, {"largura_min_crista": 4})
    assert por_nome(ex)["crista"].severidade is Severidade.AVISO


@pytest.mark.parametrize(
    ("crista", "severidade"),
    [(536.5, Severidade.OK), (535.8, Severidade.ALERTA), (535.5, Severidade.CRITICO), (535.0, Severidade.CRITICO)],
)
def test_borda_livre(crista, severidade):
    ex = executar("geometria.borda_livre", {"cota_crista": crista, "cota_na_maximo": 535.5})
    bl = por_nome(ex)["borda_livre"]
    assert bl.valor == pytest.approx(crista - 535.5)
    assert (bl.severidade, bl.limite) == (severidade, 1.0)


def test_catalogo_m7():
    assert {k for k in REGISTRO if k.startswith("geometria.")} == {
        "geometria.secao_macico",
        "geometria.volume_terra",
        "geometria.borda_livre",
    }
    nomes = [lim["nome"] for lim in REGISTRO["geometria.secao_macico"].para_dict()["limites"]]
    assert nomes == ["largura_min_crista", "talude_min_montante", "talude_min_jusante"]
