from datetime import datetime, timedelta, timezone

import pytest

from damiq_calc.core.resultado import Severidade
from damiq_calc.medicoes.modelo import FlagQualidade, Medicao, TipoMedicao
from damiq_calc.monitoramento import (
    Categoria,
    ConfigMonitoramento,
    DirecaoTaxa,
    LimitesAlerta,
    Niveis,
    ParametrosAnomalia,
    ParametrosTravado,
    RegrasSensor,
    TaxaVariacao,
    TipoAlerta,
    avaliar,
)
from damiq_calc.monitoramento import regras

BRT = timezone(timedelta(hours=-3))
T0 = datetime(2026, 9, 29, 0, 0, tzinfo=BRT)

# Desliga as regras de qualidade para isolar a regra testada.
SEM_QUALIDADE = {
    "anomalia": ParametrosAnomalia(ativo=False),
    "travado": ParametrosTravado(ativo=False),
}

PZ_LIMITES = LimitesAlerta(acima=Niveis(aviso=180, alerta=220, critico=260))


def serie(valores, sensor="PZ-01", tipo=TipoMedicao.PRESSAO, unidade="kPa", passo_h=1, inicio=T0, flags=None):
    flags = flags or {}
    return [
        Medicao(
            sensor=sensor,
            tipo=tipo,
            timestamp=inicio + timedelta(hours=i * passo_h),
            valor=float(v),
            unidade=unidade,
            valor_original=float(v),
            unidade_original=unidade,
            flags=flags.get(i, ()),
        )
        for i, v in enumerate(valores)
    ]


def config(sensores=None, **kwargs):
    return ConfigMonitoramento(sensores=sensores or {}, **{**SEM_QUALIDADE, **kwargs})


# --- regras isoladas ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("valor", "esperado"),
    [(100, Severidade.OK), (180, Severidade.AVISO), (219.9, Severidade.AVISO), (220, Severidade.ALERTA), (300, Severidade.CRITICO)],
)
def test_classificar_limite_acima(valor, esperado):
    assert regras.classificar_limite(valor, PZ_LIMITES)[0] is esperado


def test_classificar_limite_abaixo():
    limites = LimitesAlerta(abaixo=Niveis(aviso=745, critico=740))
    assert regras.classificar_limite(746, limites)[0] is Severidade.OK
    assert regras.classificar_limite(744, limites)[:2] == (Severidade.AVISO, 745)
    assert regras.classificar_limite(739, limites)[:2] == (Severidade.CRITICO, 740)


def test_taxa_extrapolada_para_o_intervalo():
    # 0,2 m em 30 min = 0,4 m/h
    assert regras.taxa_no_intervalo(10.0, 10.2, timedelta(minutes=30), timedelta(hours=1)) == pytest.approx(0.4)


@pytest.mark.parametrize(
    ("direcao", "taxa", "esperado"),
    [
        (DirecaoTaxa.DESCIDA, -0.6, Severidade.ALERTA),
        (DirecaoTaxa.DESCIDA, 0.6, Severidade.OK),
        (DirecaoTaxa.SUBIDA, 0.6, Severidade.ALERTA),
        (DirecaoTaxa.AMBAS, -1.2, Severidade.CRITICO),
    ],
)
def test_classificar_taxa(direcao, taxa, esperado):
    regra = TaxaVariacao(niveis=Niveis(aviso=0.2, alerta=0.5, critico=1.0), direcao=direcao)
    assert regras.classificar_taxa(taxa, regra)[0] is esperado


def test_z_modificado():
    janela = [10, 11, 10, 12, 11, 10, 11]
    assert regras.z_modificado(11, janela) == pytest.approx(0.0)
    assert regras.z_modificado(20, janela) == pytest.approx(0.6745 * 9 / 1)
    assert regras.z_modificado(5, [7, 7, 7]) is None  # MAD = 0


def test_sequencias_iguais():
    assert regras.sequencias_iguais([1, 2, 2, 2, 3, 3, 4, 4, 4, 4], 3) == [(1, 3), (6, 9)]
    assert regras.sequencias_iguais([], 3) == []


# --- avaliação do lote ----------------------------------------------------------------


def test_episodio_agrupa_leituras_consecutivas():
    lote = serie([150, 190, 230, 270, 200, 150, 185])
    r = avaliar(lote, config({"PZ-01": RegrasSensor(limites=PZ_LIMITES)}))
    assert [(a.inicio.hour, a.fim.hour, a.leituras, a.severidade, a.valor_extremo) for a in r.alertas] == [
        (1, 4, 4, Severidade.CRITICO, 270.0),
        (6, 6, 1, Severidade.AVISO, 185.0),
    ]
    [primeiro, _] = r.alertas
    assert primeiro.limite == 260
    assert primeiro.categoria is Categoria.SEGURANCA
    assert "acima do limite de critico" in primeiro.mensagem
    assert r.status_barragem is Severidade.CRITICO
    assert r.status_dados is Severidade.OK


def test_situacao_do_sensor():
    lote = serie([150, 270, 190])
    r = avaliar(lote, config({"PZ-01": RegrasSensor(limites=PZ_LIMITES)}))
    sit = r.sensores["PZ-01"]
    assert sit.status_atual is Severidade.AVISO  # última leitura: 190
    assert sit.status_maximo is Severidade.CRITICO
    assert sit.ultima.valor == 190


def test_limite_abaixo_no_nivel_do_reservatorio():
    lote = serie([748, 746, 744, 739], sensor="RN-01", tipo=TipoMedicao.NIVEL, unidade="m")
    regra = RegrasSensor(limites=LimitesAlerta(abaixo=Niveis(aviso=745, critico=740)))
    [alerta] = avaliar(lote, config({"RN-01": regra})).alertas
    assert (alerta.severidade, alerta.valor_extremo, alerta.direcao) == (Severidade.CRITICO, 739.0, "abaixo")


def test_rebaixamento_rapido_usa_historico_como_contexto():
    """O primeiro ponto do lote é comparado com a última leitura do histórico."""
    historico = serie([750.0, 750.0], sensor="RN-01", tipo=TipoMedicao.NIVEL, unidade="m")
    lote = serie([749.3, 749.2], sensor="RN-01", tipo=TipoMedicao.NIVEL, unidade="m", inicio=T0 + timedelta(hours=2))
    regra = RegrasSensor(
        taxa=TaxaVariacao(niveis=Niveis(aviso=0.2, alerta=0.5), intervalo=timedelta(hours=1), direcao=DirecaoTaxa.DESCIDA)
    )
    [alerta] = avaliar(lote, config({"RN-01": regra}), historico).alertas
    assert alerta.tipo is TipoAlerta.TAXA_VARIACAO
    assert alerta.severidade is Severidade.ALERTA
    assert alerta.leituras == 1
    assert alerta.valor_extremo == pytest.approx(-0.7)
    assert alerta.unidade == "m/h"
    assert alerta.direcao == "descida"


def test_historico_nao_gera_alertas():
    historico = serie([300, 300])  # acima do crítico, mas só contexto
    lote = serie([150], inicio=T0 + timedelta(hours=2))
    r = avaliar(lote, config({"PZ-01": RegrasSensor(limites=PZ_LIMITES)}), historico)
    assert r.alertas == []


def test_historico_duplicado_com_lote_e_descartado():
    historico = serie([300])
    lote = serie([150])  # mesmo timestamp
    r = avaliar(lote, config({"PZ-01": RegrasSensor(taxa=TaxaVariacao(niveis=Niveis(aviso=1)))}), historico)
    assert r.alertas == []


def test_fora_da_faixa_vira_alerta_de_qualidade_e_marca_suspeita():
    lote = serie([150, 900, 150], flags={1: (FlagQualidade.FORA_FAIXA_PLAUSIVEL,)})
    r = avaliar(lote, config({"PZ-01": RegrasSensor(limites=PZ_LIMITES)}))
    por_tipo = {a.tipo: a for a in r.alertas}
    assert por_tipo[TipoAlerta.FORA_FAIXA_PLAUSIVEL].categoria is Categoria.QUALIDADE
    # o limite continua sendo avaliado (conservador), mas sinalizado como suspeito
    assert por_tipo[TipoAlerta.LIMITE].leitura_suspeita is True
    assert r.status_dados is Severidade.AVISO


def test_sensor_travado():
    lote = serie([12.0] * 5 + [12.5])
    r = avaliar(lote, config(travado=ParametrosTravado(ativo=True, leituras_consecutivas=4)))
    [alerta] = r.alertas
    assert (alerta.tipo, alerta.leituras, alerta.categoria) == (TipoAlerta.SENSOR_TRAVADO, 5, Categoria.QUALIDADE)
    assert r.status_barragem is Severidade.OK


def test_travado_so_no_historico_nao_alerta():
    historico = serie([12.0] * 5)
    lote = serie([12.5], inicio=T0 + timedelta(hours=5))
    assert avaliar(lote, config(travado=ParametrosTravado(ativo=True, leituras_consecutivas=4)), historico).alertas == []


def test_anomalia_estatistica():
    valores = [100, 101, 99, 100, 102, 101, 100, 99, 101, 100, 140]
    r = avaliar(serie(valores), config(anomalia=ParametrosAnomalia(janela_leituras=10, minimo_leituras=8)))
    [alerta] = r.alertas
    assert alerta.tipo is TipoAlerta.ANOMALIA_ESTATISTICA
    assert alerta.valor_extremo == 140
    assert alerta.detalhe["z"] > 3.5


def test_anomalia_exige_minimo_de_leituras():
    r = avaliar(serie([100, 101, 140]), config(anomalia=ParametrosAnomalia(minimo_leituras=8)))
    assert r.alertas == []


def test_sensor_sem_regras_so_recebe_situacao():
    r = avaliar(serie([150]), config())
    assert r.alertas == []
    assert r.sensores["PZ-01"].status_atual is Severidade.OK


def test_desempenho_rnf01():
    """500 leituras com todas as regras ativas, bem abaixo do limite de 30 s."""
    import time

    valores = [100 + (i % 7) for i in range(500)]
    lote = []
    for s in range(10):
        lote += serie(valores[:50], sensor=f"PZ-{s:02d}")
    cfg = ConfigMonitoramento(
        sensores={f"PZ-{s:02d}": RegrasSensor(limites=PZ_LIMITES, taxa=TaxaVariacao(niveis=Niveis(aviso=50))) for s in range(10)}
    )
    inicio = time.perf_counter()
    avaliar(lote, cfg)
    assert time.perf_counter() - inicio < 2.0


def test_padroes_para_leitura_manual():
    """Leituras digitadas/importadas: taxa por dia e detecção de sensor travado desligada."""
    assert TaxaVariacao(niveis=Niveis(aviso=1)).intervalo == timedelta(days=1)
    assert ParametrosTravado().ativo is False
    r = avaliar(serie([12.0] * 20), ConfigMonitoramento(anomalia=ParametrosAnomalia(ativo=False)))
    assert r.alertas == []
