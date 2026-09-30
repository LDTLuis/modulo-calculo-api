import pytest

from damiq_calc.core import unidades
from damiq_calc.core.erros import UnidadeDesconhecida, UnidadeIncompativel
from damiq_calc.core.unidades import Dimensao


@pytest.mark.parametrize(
    ("valor", "de", "para", "esperado"),
    [
        (1.0, "m", "mm", 1000.0),
        (250.0, "cm", "m", 2.5),
        (1.0, "bar", "kPa", 100.0),
        (1.0, "mca", "kPa", 9.81),
        (19.62, "kPa", "mca", 2.0),
        (1.0, "psi", "kPa", 6.894757),
        (1000.0, "L/s", "m3/s", 1.0),
        (3600.0, "m3/h", "m3/s", 1.0),
        (1.0, "km2", "ha", 100.0),
        (3.0, "hm3", "m3", 3_000_000.0),
        (5.0, "cm/s", "m/s", 0.05),
        (50.0, "%", "-", 0.5),
    ],
)
def test_converter(valor, de, para, esperado):
    assert unidades.converter(valor, de, para) == pytest.approx(esperado)


@pytest.mark.parametrize("grafia", ["m³/s", "M3/S", " m3/s ", "m 3/s"])
def test_normaliza_grafias(grafia):
    assert unidades.normalizar_unidade(grafia) == "m3/s"


@pytest.mark.parametrize("grafia", ["mH2O", "m.c.a.", "MCA"])
def test_aliases_de_coluna_dagua(grafia):
    assert unidades.nome_canonico(grafia) == "mca"


def test_dimensao():
    assert unidades.dimensao("km²") is Dimensao.AREA
    assert unidades.dimensao("kN/m³") is Dimensao.PESO_ESPECIFICO


def test_converter_aceita_arrays_numpy():
    np = pytest.importorskip("numpy")
    resultado = unidades.converter(np.array([1.0, 2.0]), "m", "cm")
    assert list(resultado) == [100.0, 200.0]


def test_unidade_desconhecida():
    with pytest.raises(UnidadeDesconhecida):
        unidades.converter(1, "furlong", "m")


def test_unidade_incompativel():
    with pytest.raises(UnidadeIncompativel):
        unidades.converter(1, "m", "kPa")
