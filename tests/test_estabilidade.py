"""M5 – estabilidade.

A apostila cita os métodos (Fellenius, Bishop; NBR 11.682 FS ≥ 1,5) sem exercício resolvido
de fatias, então os taludes são verificados contra soluções analíticas exatas. A barragem de
gravidade usa o critério da apostila (P·f ≥ E·n, f = 0,75, n = 1,5 ⇒ P ≥ 2E) e casos
conferidos à mão.
"""

import math

import pytest

from damiq_calc.adapters.contrato import processar
from damiq_calc.catalogo import REGISTRO, executar
from damiq_calc.core.calculo import ErroEntradas
from damiq_calc.core.resultado import Severidade


def fs_de(ex):
    [r] = [r for r in ex.resultados if r.calculo.endswith(".fs")]
    return r


def fatias_iguais(n=4, alfa=20.0, phi=30.0, coesao=0.0, peso=100.0, largura=2.0, poropressao=None):
    linha = {"largura": largura, "peso": peso, "alfa": alfa, "coesao": coesao, "phi": phi}
    if poropressao is not None:
        linha["poropressao"] = poropressao
    return [dict(linha) for _ in range(n)]


# Superfície circular típica: α cresce do pé para o topo.
FATIAS_CIRCULO = [
    {"largura": 2.0, "peso": 40.0, "alfa": -10.0, "coesao": 10.0, "phi": 28.0},
    {"largura": 2.0, "peso": 110.0, "alfa": 5.0, "coesao": 10.0, "phi": 28.0},
    {"largura": 2.0, "peso": 160.0, "alfa": 18.0, "coesao": 10.0, "phi": 28.0},
    {"largura": 2.0, "peso": 170.0, "alfa": 32.0, "coesao": 10.0, "phi": 28.0},
    {"largura": 2.0, "peso": 120.0, "alfa": 47.0, "coesao": 10.0, "phi": 28.0},
    {"largura": 2.0, "peso": 45.0, "alfa": 63.0, "coesao": 10.0, "phi": 28.0},
]


# --- taludes ----------------------------------------------------------------------------


@pytest.mark.parametrize("metodo", ["estabilidade.talude_fellenius", "estabilidade.talude_bishop"])
def test_solo_sem_coesao_com_alfa_constante(metodo):
    """c' = 0, u = 0, α constante: os dois métodos dão exatamente FS = tan φ / tan α."""
    fs = fs_de(executar(metodo, {"fatias": fatias_iguais(alfa=20, phi=30)}))
    assert fs.valor == pytest.approx(math.tan(math.radians(30)) / math.tan(math.radians(20)), rel=1e-6)
    assert (fs.severidade, fs.limite) == (Severidade.OK, 1.5)


@pytest.mark.parametrize("metodo", ["estabilidade.talude_fellenius", "estabilidade.talude_bishop"])
def test_solo_puramente_coesivo(metodo):
    """φ' = 0: FS = Σ c·l / Σ W·sen α nos dois métodos (= 0,9238 aqui → CRITICO)."""
    fs = fs_de(executar(metodo, {"fatias": fatias_iguais(alfa=30, phi=0, coesao=20)}))
    esperado = 20 * (2 / math.cos(math.radians(30))) / (100 * math.sin(math.radians(30)))
    assert fs.valor == pytest.approx(esperado, rel=1e-6)
    assert fs.severidade is Severidade.CRITICO


def test_bishop_converge_e_supera_fellenius_em_superficie_circular():
    fell = fs_de(executar("estabilidade.talude_fellenius", {"fatias": FATIAS_CIRCULO})).valor
    ex = executar("estabilidade.talude_bishop", {"fatias": FATIAS_CIRCULO})
    bishop = fs_de(ex).valor
    assert bishop > fell  # Fellenius é conservador

    # o FS devolvido satisfaz a equação de Bishop
    ss = sum(f["peso"] * math.sin(math.radians(f["alfa"])) for f in FATIAS_CIRCULO)
    sr = 0.0
    for f in FATIAS_CIRCULO:
        a, t = math.radians(f["alfa"]), math.tan(math.radians(f["phi"]))
        sr += (f["coesao"] * f["largura"] + f["peso"] * t) / (math.cos(a) + math.sin(a) * t / bishop)
    assert sr / ss == pytest.approx(bishop, rel=1e-6)
    assert ex.memoria.tabelas[0]["titulo"].startswith("Bishop")
    assert len(ex.memoria.tabelas[0]["linhas"]) == len(FATIAS_CIRCULO)


def test_poropressao_reduz_o_fs():
    seco = fs_de(executar("estabilidade.talude_bishop", {"fatias": FATIAS_CIRCULO})).valor
    saturado = [{**f, "poropressao": 20.0} for f in FATIAS_CIRCULO]
    assert fs_de(executar("estabilidade.talude_bishop", {"fatias": saturado})).valor < seco


def test_poropressao_padrao_vira_premissa():
    ex = executar("estabilidade.talude_fellenius", {"fatias": fatias_iguais()})
    assert "fatias.poropressao = 0 kPa (padrão)" in ex.memoria.premissas
    assert "fs_min_talude = 1,5 (padrão do motor)" in ex.memoria.premissas


def test_unidades_nas_fatias():
    em_si = fs_de(executar("estabilidade.talude_bishop", {"fatias": FATIAS_CIRCULO})).valor
    convertidas = [
        {**f, "peso": {"valor": f["peso"] / 9.80665, "unidade": "tf/m"}, "alfa": {"valor": math.radians(f["alfa"]), "unidade": "rad"}}
        for f in FATIAS_CIRCULO
    ]
    assert fs_de(executar("estabilidade.talude_bishop", {"fatias": convertidas})).valor == pytest.approx(em_si)


def test_limite_da_central():
    ex = executar("estabilidade.talude_fellenius", {"fatias": fatias_iguais(alfa=20, phi=30)}, {"fs_min_talude": 1.8})
    assert fs_de(ex).severidade is Severidade.ALERTA  # 1,59 < 1,8
    assert "não atende à NBR 11.682" in ex.memoria.conclusoes[0]


def test_erros_por_celula():
    fatias = fatias_iguais(n=3)
    fatias[1]["alfa"] = 95
    fatias[2]["coesao"] = -1
    fatias[2]["extra"] = 1
    del fatias[0]["peso"]
    with pytest.raises(ErroEntradas) as exc:
        executar("estabilidade.talude_bishop", {"fatias": fatias})
    assert {(e["campo"], e["codigo"]) for e in exc.value.erros} == {
        ("fatias[0].peso", "CAMPO_AUSENTE"),
        ("fatias[1].alfa", "FORA_DO_INTERVALO"),
        ("fatias[2].coesao", "FORA_DO_INTERVALO"),
        ("fatias[2].extra", "CAMPO_DESCONHECIDO"),
    }


@pytest.mark.parametrize("fatias", [None, [], "fatias"])
def test_tabela_ausente_ou_invalida(fatias):
    entradas = {} if fatias is None else {"fatias": fatias}
    with pytest.raises(ErroEntradas) as exc:
        executar("estabilidade.talude_fellenius", entradas)
    assert exc.value.erros[0]["campo"] == "fatias"


def test_sem_esforco_instabilizante():
    with pytest.raises(ErroEntradas) as exc:
        executar("estabilidade.talude_bishop", {"fatias": fatias_iguais(alfa=-15)})
    assert "Σ W·sen α ≤ 0" in exc.value.erros[0]["mensagem"]


# --- gravidade: escorregamento -----------------------------------------------------------


def test_deslizamento_criterio_da_apostila():
    """AP: P·0,75 = E·1,50 ⇒ P = 2E está exatamente no limite."""
    ex = executar("estabilidade.gravidade_deslizamento", {"peso": 2000, "empuxo": 1000})
    r = {x.calculo.rsplit(".", 1)[-1]: x for x in ex.resultados}
    assert r["fs"].valor == pytest.approx(1.5)
    assert r["fs"].severidade is Severidade.OK
    assert r["peso_minimo"].valor == pytest.approx(2000)
    assert "coeficiente_atrito = 0,75 (padrão)" in ex.memoria.premissas


def test_deslizamento_subpressao_reduz_fs():
    ex = executar("estabilidade.gravidade_deslizamento", {"peso": 2000, "empuxo": 1000, "subpressao": 500})
    r = {x.calculo.rsplit(".", 1)[-1]: x for x in ex.resultados}
    assert r["fs"].valor == pytest.approx(1.125)
    assert r["fs"].severidade is Severidade.ALERTA
    assert r["peso_minimo"].valor == pytest.approx(2500)
    assert "peso necessário ≥ 2500 kN/m" in ex.memoria.conclusoes[0]


def test_deslizamento_flutuacao():
    ex = executar("estabilidade.gravidade_deslizamento", {"peso": 400, "empuxo": 100, "subpressao": 500})
    assert fs_de(ex).severidade is Severidade.CRITICO
    assert "flutuação" in ex.memoria.conclusoes[0]


# --- gravidade: resultante ---------------------------------------------------------------

# Perfil triangular, paramento de montante vertical: B = H = 10 m, γc = 24 kN/m³, γw = 10.
# P = 24·10·10/2 = 1200 kN/m em x = B/3; E = 10·10²/2 = 500 kN/m em y = H/3.
TRIANGULAR = {"largura_base": 10, "peso": 1200, "braco_peso": 10 / 3, "empuxo": 500, "altura_empuxo": 10 / 3}


def resultados_resultante(entradas):
    ex = executar("estabilidade.gravidade_resultante", entradas)
    return ex, {x.calculo.rsplit(".", 1)[-1]: x for x in ex.resultados}


def test_resultante_no_terco_medio():
    # M = 1200·10/3 + 500·10/3 = 5666,7; x_R = 4,722; e = −0,278; σ = 120·(1 ± 1/6) → 140 e 100 kPa
    ex, r = resultados_resultante(TRIANGULAR)
    assert r["posicao"].valor == pytest.approx(5666.6667 / 1200)
    assert r["posicao"].severidade is Severidade.OK
    assert r["excentricidade"].limite == pytest.approx(10 / 6)
    assert r["tensao_montante"].valor == pytest.approx(140.0)
    assert r["tensao_jusante"].valor == pytest.approx(100.0)
    assert "terço médio" in ex.memoria.conclusoes[0]


def test_resultante_com_subpressao_triangular():
    # U = 10·100/2 = 500 kN/m em x = B/3 → N = 700; M = 4000; x_R = 5,714 (ainda no terço médio)
    _, r = resultados_resultante({**TRIANGULAR, "subpressao": 500, "braco_subpressao": 10 / 3})
    assert r["normal"].valor == pytest.approx(700)
    assert r["posicao"].valor == pytest.approx(4000 / 700)
    assert r["posicao"].severidade is Severidade.OK


@pytest.mark.parametrize(("empuxo", "esperado"), [(2000, Severidade.ALERTA), (4000, Severidade.CRITICO)])
def test_resultante_fora_do_terco_medio_e_fora_da_base(empuxo, esperado):
    _, r = resultados_resultante({**TRIANGULAR, "empuxo": empuxo})
    assert r["posicao"].severidade is esperado


def test_resultante_braco_maior_que_a_base():
    with pytest.raises(ErroEntradas) as exc:
        executar("estabilidade.gravidade_resultante", {**TRIANGULAR, "braco_peso": 12})
    assert exc.value.erros[0]["campo"] == "braco_peso"


def test_encadeamento_m3_para_m5():
    """O empuxo e a subpressão do M3 alimentam a verificação de gravidade."""
    emp = executar("hidrostatica.empuxo", {"altura_agua": 10, "gama_w": 10})
    eh = next(r.valor for r in emp.resultados if r.calculo.endswith(".horizontal"))
    y = next(r.valor for r in emp.resultados if r.calculo.endswith(".braco_horizontal"))
    _, r = resultados_resultante({**TRIANGULAR, "empuxo": eh, "altura_empuxo": y})
    assert r["tensao_montante"].valor == pytest.approx(140.0)


# --- contrato e catálogo -------------------------------------------------------------------


def test_calcular_talude_via_contrato():
    resp = processar(
        {
            "versao_contrato": "1.0",
            "operacao": "calcular",
            "calculo": "estabilidade.talude_bishop",
            "configuracao": {"versao": 3, "limites_calculo": {"fs_min_talude": 1.5}},
            "entradas": {"fatias": FATIAS_CIRCULO},
        }
    )
    assert resp["status"] == "OK"
    assert resp["memoria"]["tabelas"][0]["colunas"][0] == {"nome": "b", "unidade": "m"}
    assert resp["entradas"]["fatias"]["valor"][0]["poropressao"] == 0.0
    assert "fs_min_talude = 1,5 (configuração da Central)" in resp["memoria"]["premissas"]


def test_descoberta_de_tabela():
    d = REGISTRO["estabilidade.talude_bishop"].para_dict()
    [fatias] = d["entradas"]
    assert fatias["tipo"] == "tabela"
    assert [c["nome"] for c in fatias["colunas"]] == ["largura", "peso", "alfa", "coesao", "phi", "poropressao"]
    alfa = fatias["colunas"][2]
    assert alfa["unidades_aceitas"] == ["grau", "rad"]
    assert (alfa["maximo"], alfa["maximo_inclusivo"]) == (90, False)
    assert {k for k in REGISTRO if k.startswith("estabilidade.")} == {
        "estabilidade.talude_fellenius",
        "estabilidade.talude_bishop",
        "estabilidade.gravidade_deslizamento",
        "estabilidade.gravidade_resultante",
    }
