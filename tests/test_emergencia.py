"""M9 – emergência / PAE."""

import pytest

from damiq_calc.adapters.contrato import processar
from damiq_calc.catalogo import REGISTRO, executar
from damiq_calc.core.calculo import ErroEntradas
from damiq_calc.core.resultado import Severidade
from damiq_calc.emergencia import nivel_de_resposta


def por_nome(ex):
    return {r.calculo.rsplit(".", 1)[-1]: r for r in ex.resultados}


@pytest.mark.parametrize(
    ("severidade", "nivel", "cor"),
    [(Severidade.OK, 0, None), (Severidade.AVISO, 1, "verde"), (Severidade.ALERTA, 2, "amarelo"), (Severidade.CRITICO, 3, "vermelho")],
)
def test_mapeamento_de_niveis(severidade, nivel, cor):
    n = nivel_de_resposta(severidade)
    assert (n.nivel, n.cor) == (nivel, cor)
    assert n.acoes


def test_calculo_nivel_resposta():
    ex = executar("emergencia.nivel_resposta", {"severidade": 3})
    r = por_nome(ex)["nivel"]
    assert (r.valor, r.rotulo, r.severidade) == (3, "Nível 3 – vermelho", Severidade.CRITICO)
    assert any("sirenes" in c for c in ex.memoria.conclusoes)


def test_nivel_resposta_invalido():
    with pytest.raises(ErroEntradas):
        executar("emergencia.nivel_resposta", {"severidade": 4})


SECOES = [
    {"distancia": 0, "tempo_chegada": 0},
    {"distancia": 2, "tempo_chegada": 10},
    {"distancia": 5, "tempo_chegada": 25},
    {"distancia": 8, "tempo_chegada": 45},
    {"distancia": 15, "tempo_chegada": 90},
]


def test_zas_governada_pelo_tempo():
    # entre 5 km (25 min) e 8 km (45 min): d(30) = 5 + 3·5/20 = 5,75 km < 10 km
    ex = executar("emergencia.zas", {"secoes": SECOES})
    z = por_nome(ex)["extensao"]
    assert z.valor == pytest.approx(5.75)
    assert "tempo de chegada de 30 min" in ex.memoria.conclusoes[0]


def test_zas_governada_pela_distancia():
    """Onda lenta: em 30 min passa de 10 km → ZAS = 10 km (critério do guia da ANA)."""
    rapida = [{"distancia": 0, "tempo_chegada": 0}, {"distancia": 20, "tempo_chegada": 40}]
    ex = executar("emergencia.zas", {"secoes": rapida})
    assert por_nome(ex)["extensao"].valor == pytest.approx(10.0)
    assert "distância máxima" in ex.memoria.conclusoes[0]


def test_zas_estudo_curto_gera_aviso():
    curto = [{"distancia": 0, "tempo_chegada": 0}, {"distancia": 4, "tempo_chegada": 20}]
    z = por_nome(executar("emergencia.zas", {"secoes": curto}))["extensao"]
    assert (z.valor, z.severidade) == (4.0, Severidade.AVISO)


def test_zas_em_metros_e_horas():
    secoes = [{"distancia": {"valor": 0, "unidade": "m"}, "tempo_chegada": 0}, {"distancia": {"valor": 8000, "unidade": "m"}, "tempo_chegada": {"valor": 1, "unidade": "h"}}]
    assert por_nome(executar("emergencia.zas", {"secoes": secoes}))["extensao"].valor == pytest.approx(4.0)


def test_zas_tempo_decrescente():
    with pytest.raises(ErroEntradas):
        executar("emergencia.zas", {"secoes": [{"distancia": 0, "tempo_chegada": 10}, {"distancia": 5, "tempo_chegada": 5}]})


def test_processar_lote_traz_nivel_de_resposta():
    resp = processar(
        {
            "versao_contrato": "1.0",
            "operacao": "processar_lote",
            "configuracao": {
                "versao": 1,
                "sensores": {"PZ-01": {"tipo": "pressao", "limites_alerta": {"acima": {"aviso": 180, "alerta": 220, "critico": 260}}}},
            },
            "opcoes": {"agora": "2026-09-30T12:00:00-03:00"},
            "medicoes": [{"sensor": "PZ-01", "tipo": "pressao", "timestamp": "2026-09-29T08:00:00", "valor": 230, "unidade": "kPa"}],
        }
    )
    nivel = resp["monitoramento"]["nivel_resposta"]
    assert (nivel["nivel"], nivel["cor"]) == (2, "amarelo")


def test_catalogo_m9():
    assert {k for k in REGISTRO if k.startswith("emergencia.")} == {"emergencia.nivel_resposta", "emergencia.zas"}
