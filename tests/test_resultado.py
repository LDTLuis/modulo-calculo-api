from damiq_calc.core.resultado import Resultado, Severidade, severidade_maxima


def test_severidade_maxima():
    assert severidade_maxima([Severidade.AVISO, Severidade.CRITICO, Severidade.OK]) is Severidade.CRITICO
    assert severidade_maxima([]) is Severidade.OK


def test_resultado_para_dict():
    r = Resultado(
        calculo="percolacao.fs_piping",
        valor=2.16,
        unidade="-",
        limite=1.5,
        premissas=("gamma_w=10 kN/m3",),
        fonte="AP, Nota 11",
    )
    assert r.para_dict() == {
        "calculo": "percolacao.fs_piping",
        "descricao": None,
        "valor": 2.16,
        "unidade": "-",
        "status": "OK",
        "limite": 1.5,
        "premissas": ["gamma_w=10 kN/m3"],
        "fonte": "AP, Nota 11",
        "rotulo": None,
    }
