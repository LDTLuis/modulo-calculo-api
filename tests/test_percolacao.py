"""M4 – casos de referência da apostila BCST, Nota 11 (redes de fluxo e piping)."""

import pytest

from damiq_calc.adapters.contrato import processar
from damiq_calc.adapters.leitura import ErroContrato
from damiq_calc.catalogo import REGISTRO, executar
from damiq_calc.core.calculo import ErroEntradas, classificar_fs
from damiq_calc.core.resultado import Severidade


def por_nome(execucao):
    return {r.calculo.rsplit(".", 1)[-1]: r for r in execucao.resultados}


# --- Darcy e vazão ----------------------------------------------------------------------


def test_darcy_elemento_da_rede():
    """AP slide 513: elemento com Δh = 1 cm, l = 2 cm, b = 2 cm, k = 0,05 cm/s → i = 0,5; Q = 0,05 cm³/s/cm."""
    ex = executar(
        "percolacao.darcy",
        {
            "k": {"valor": 0.05, "unidade": "cm/s"},
            "perda_carga": {"valor": 1, "unidade": "cm"},
            "comprimento_percurso": {"valor": 2, "unidade": "cm"},
            "area": {"valor": 2e-4, "unidade": "m2"},  # 2 cm × 1 cm de largura
        },
    )
    r = por_nome(ex)
    assert r["gradiente"].valor == pytest.approx(0.5)
    assert r["vazao"].valor == pytest.approx(0.05e-6)  # 0,05 cm³/s


def test_darcy_gradiente_no_ponto_a():
    """AP slide 561: i = 1,1 / 6 ≈ 0,18."""
    r = por_nome(executar("percolacao.darcy", {"k": 1e-4, "perda_carga": 1.1, "comprimento_percurso": 6}))
    assert r["gradiente"].valor == pytest.approx(0.1833, abs=1e-4)
    assert "vazao" not in r


@pytest.mark.parametrize(
    ("entradas", "esperado"),
    [
        # AP slide 513: Q = 0,05 · 6 · 4 / 6 = 0,2 cm³/s/cm = 2·10⁻⁵ m³/s/m
        ({"k": {"valor": 0.05, "unidade": "cm/s"}, "perda_carga_total": {"valor": 6, "unidade": "cm"}, "n_f": 4, "n_d": 6}, 2e-5),
        # AP slide 536: Q = 1·10⁻⁴ · 15,4 · 5 / 14 = 5,5·10⁻⁴ m³/s/m
        ({"k": 1e-4, "perda_carga_total": 15.4, "n_f": 5, "n_d": 14}, 5.5e-4),
    ],
)
def test_vazao_rede_fluxo(entradas, esperado):
    assert por_nome(executar("percolacao.vazao_rede_fluxo", entradas))["por_metro"].valor == pytest.approx(esperado)


def test_vazao_total_com_comprimento():
    ex = executar("percolacao.vazao_rede_fluxo", {"k": 1e-4, "perda_carga_total": 15.4, "n_f": 5, "n_d": 14, "comprimento": 56})
    assert por_nome(ex)["total"].valor == pytest.approx(5.5e-4 * 56)


# --- piping -----------------------------------------------------------------------------

EXERCICIO_2 = {"perda_carga_total": 15.4, "n_d": 14, "comprimento_celula": 3, "gama_sat": 18, "gama_w": 10}


def test_piping_exercicio_2_da_apostila():
    """AP Ex. 2: i_crit = (18 − 10)/10 = 0,8; i = 1,1/3 = 0,37; FS = 0,8/0,37 ≈ 2,2."""
    ex = executar("percolacao.piping", EXERCICIO_2)
    r = por_nome(ex)
    assert r["delta_h"].valor == pytest.approx(1.1)
    assert r["gradiente_saida"].valor == pytest.approx(0.3667, abs=1e-4)
    assert r["gradiente_critico"].valor == pytest.approx(0.8)
    assert r["fs"].valor == pytest.approx(2.18, abs=0.01)
    assert (r["fs"].severidade, r["fs"].limite) == (Severidade.OK, 1.5)
    assert "fs_min_piping = 1,5 (padrão do motor)" in ex.memoria.premissas
    assert ex.memoria.conclusoes == ["FS = 2,18 ≥ 1,5: atende ao critério contra areia movediça."]


def test_piping_com_limite_da_central():
    ex = executar("percolacao.piping", EXERCICIO_2, {"fs_min_piping": 2.5})
    fs = por_nome(ex)["fs"]
    assert (fs.severidade, fs.limite) == (Severidade.ALERTA, 2.5)
    assert "fs_min_piping = 2,5 (configuração da Central)" in ex.memoria.premissas
    assert ex.memoria.conclusoes[0].startswith("FS = 2,18 < 2,5: não atende")


def test_piping_fs_abaixo_de_1_e_critico():
    ex = executar("percolacao.piping", {**EXERCICIO_2, "comprimento_celula": 0.5})
    assert por_nome(ex)["fs"].severidade is Severidade.CRITICO


def test_piping_gama_sat_menor_que_gama_w():
    with pytest.raises(ErroEntradas) as exc:
        executar("percolacao.piping", {**EXERCICIO_2, "gama_sat": 9})
    assert exc.value.erros[0]["campo"] == "gama_sat"


@pytest.mark.parametrize(
    ("fs", "esperado"),
    [(2.0, Severidade.OK), (1.5, Severidade.OK), (1.2, Severidade.ALERTA), (1.0, Severidade.ALERTA), (0.9, Severidade.CRITICO)],
)
def test_classificar_fs(fs, esperado):
    assert classificar_fs(fs, 1.5) is esperado


# --- filtros de Terzaghi ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("d15_filtro", "permeabilidade", "retencao"),
    [
        (0.5, Severidade.OK, Severidade.OK),  # material "Q": satisfaz os dois critérios
        (0.05, Severidade.ALERTA, Severidade.OK),  # material "P": pouco permeável
        (2.0, Severidade.OK, Severidade.ALERTA),  # material "R": deixa passar os finos
    ],
)
def test_filtro_terzaghi(d15_filtro, permeabilidade, retencao):
    ex = executar("percolacao.filtro_terzaghi", {"d15_filtro": d15_filtro, "d15_solo": 0.02, "d85_solo": 0.3})
    r = por_nome(ex)
    assert r["permeabilidade"].severidade is permeabilidade
    assert r["retencao"].severidade is retencao
    assert len(ex.memoria.conclusoes) == 2


def test_filtro_d15_maior_que_d85():
    with pytest.raises(ErroEntradas):
        executar("percolacao.filtro_terzaghi", {"d15_filtro": 0.5, "d15_solo": 0.4, "d85_solo": 0.3})


# --- contrato ---------------------------------------------------------------------------


def test_calcular_via_contrato_com_limites_da_central():
    resp = processar(
        {
            "versao_contrato": "1.0",
            "operacao": "calcular",
            "calculo": "percolacao.piping",
            "configuracao": {"versao": 7, "limites_calculo": {"fs_min_piping": 2.5}},
            "entradas": EXERCICIO_2,
        }
    )
    assert resp["versao_config"] == 7
    assert resp["status_calculo"] == "ALERTA"
    assert resp["memoria"]["conclusoes"][0].startswith("FS = 2,18 < 2,5")


def test_limites_calculo_invalidos():
    with pytest.raises(ErroContrato):
        processar(
            {
                "versao_contrato": "1.0",
                "operacao": "calcular",
                "calculo": "percolacao.piping",
                "configuracao": {"versao": 7, "limites_calculo": {"fs_min_piping": 0}},
                "entradas": EXERCICIO_2,
            }
        )


def test_descoberta_publica_os_limites():
    piping = REGISTRO["percolacao.piping"].para_dict()
    assert piping["limites"] == [
        {"nome": "fs_min_piping", "descricao": "FS mínimo contra areia movediça/piping (i_crit / i_saída)", "padrao": 1.5}
    ]
    assert {k for k in REGISTRO if k.startswith("percolacao.")} == {
        "percolacao.darcy",
        "percolacao.vazao_rede_fluxo",
        "percolacao.piping",
        "percolacao.filtro_terzaghi",
    }


def test_memoria_formata_valores_pequenos():
    ex = executar("percolacao.vazao_rede_fluxo", {"k": 1e-4, "perda_carga_total": 15.4, "n_f": 5, "n_d": 14})
    assert ex.memoria.passos[0].substituicao == "Q = 0,0001 · 15,4 · 5 / 14 = 0,00055 m3/s/m"


@pytest.mark.parametrize(("valor", "texto"), [(2e-5, "2·10⁻⁵"), (1.5e-7, "1,5·10⁻⁷"), (7112.0, "7112"), (0.366667, "0,366667"), (3e9, "3·10⁹")])
def test_fmt(valor, texto):
    from damiq_calc.core.calculo import fmt

    assert fmt(valor) == texto
