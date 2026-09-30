from datetime import datetime, timedelta, timezone

import pytest

from damiq_calc.medicoes import ConfigSensor, TipoMedicao, detectar_lacunas, validar_lote
from damiq_calc.medicoes.modelo import CodigoRejeicao, FlagQualidade

BRT = timezone(timedelta(hours=-3))
AGORA = datetime(2026, 9, 30, 12, 0, tzinfo=BRT)


def registro(**sobrescrever):
    base = {
        "sensor": "PZ-01",
        "tipo": "pressao",
        "timestamp": "2026-09-30T08:00:00-03:00",
        "valor": 132.4,
        "unidade": "kPa",
    }
    base.update(sobrescrever)
    return base


def validar(registros, **kwargs):
    return validar_lote(registros, agora=AGORA, **kwargs)


def test_registro_valido_e_normalizado():
    r = validar([registro(tipo="Pressão", valor="1,5", unidade="bar")])
    assert r.rejeicoes == []
    [m] = r.medicoes
    assert m.tipo is TipoMedicao.PRESSAO
    assert m.valor == pytest.approx(150.0)
    assert m.unidade == "kPa"
    assert (m.valor_original, m.unidade_original) == (1.5, "bar")
    assert m.flags == ()


@pytest.mark.parametrize(
    ("tipo", "valor", "unidade", "esperado", "canonica"),
    [
        ("nível", 74900, "cm", 749.0, "m"),
        ("vazao", 12, "L/s", 0.012, "m3/s"),
        ("deslocamento", 0.4, "cm", 4.0, "mm"),
        ("pressao", 2, "mca", 19.62, "kPa"),
    ],
)
def test_unidade_canonica_por_tipo(tipo, valor, unidade, esperado, canonica):
    [m] = validar([registro(tipo=tipo, valor=valor, unidade=unidade)]).medicoes
    assert m.valor == pytest.approx(esperado)
    assert m.unidade == canonica


@pytest.mark.parametrize(
    ("sobrescrever", "codigo"),
    [
        ({"valor": None}, CodigoRejeicao.CAMPO_AUSENTE),
        ({"sensor": ""}, CodigoRejeicao.CAMPO_AUSENTE),
        ({"sensor": "  "}, CodigoRejeicao.SENSOR_INVALIDO),
        ({"sensor": True}, CodigoRejeicao.SENSOR_INVALIDO),
        ({"tipo": "temperatura"}, CodigoRejeicao.TIPO_INVALIDO),
        ({"timestamp": "30/09/2026 08:00"}, CodigoRejeicao.TIMESTAMP_INVALIDO),
        ({"timestamp": "2026-10-01T08:00:00-03:00"}, CodigoRejeicao.TIMESTAMP_FUTURO),
        ({"valor": "abc"}, CodigoRejeicao.VALOR_INVALIDO),
        ({"valor": "NaN"}, CodigoRejeicao.VALOR_INVALIDO),
        ({"valor": True}, CodigoRejeicao.VALOR_INVALIDO),
        ({"unidade": "atm"}, CodigoRejeicao.UNIDADE_DESCONHECIDA),
        ({"unidade": "m"}, CodigoRejeicao.UNIDADE_INCOMPATIVEL),
    ],
)
def test_rejeicoes(sobrescrever, codigo):
    r = validar([registro(**sobrescrever)])
    assert r.medicoes == []
    [rej] = r.rejeicoes
    assert (rej.indice, rej.codigo) == (0, codigo)


def test_registro_que_nao_e_objeto():
    [rej] = validar(["PZ-01;132.4"]).rejeicoes
    assert rej.codigo is CodigoRejeicao.REGISTRO_INVALIDO


def test_duplicada_mantem_a_primeira():
    r = validar([registro(valor=1), registro(valor=2, timestamp="2026-09-30T11:00:00+00:00")])
    assert [m.valor_original for m in r.medicoes] == [1]
    assert [(x.indice, x.codigo) for x in r.rejeicoes] == [(1, CodigoRejeicao.DUPLICADA)]


def test_timestamp_sem_fuso_usa_fuso_padrao():
    [m] = validar([registro(timestamp="2026-09-30T08:00:00")]).medicoes
    assert m.timestamp == datetime(2026, 9, 30, 8, 0, tzinfo=BRT)


def test_fora_da_faixa_e_mantida_com_flag():
    sensores = {"PZ-01": ConfigSensor(faixa=(0.0, 100.0))}
    [m] = validar([registro(valor=132.4)], sensores=sensores).medicoes
    assert m.flags == (FlagQualidade.FORA_FAIXA_PLAUSIVEL,)


def test_faixa_do_sensor_prevalece_sobre_a_do_tipo():
    sensores = {"PZ-01": ConfigSensor(faixa=(0.0, 200.0))}
    faixas = {TipoMedicao.PRESSAO: (0.0, 100.0)}
    [m] = validar([registro(valor=132.4)], sensores=sensores, faixas_por_tipo=faixas).medicoes
    assert m.flags == ()


def test_tipo_divergente_do_cadastro():
    sensores = {"PZ-01": ConfigSensor(tipo=TipoMedicao.NIVEL)}
    [rej] = validar([registro()], sensores=sensores).rejeicoes
    assert rej.codigo is CodigoRejeicao.TIPO_DIVERGENTE


def test_vazao_negativa_recebe_flag_pela_faixa_padrao():
    [m] = validar([registro(tipo="vazao", valor=-1, unidade="L/s")]).medicoes
    assert m.flags == (FlagQualidade.FORA_FAIXA_PLAUSIVEL,)


def test_saida_ordenada_por_sensor_e_tempo():
    r = validar(
        [
            registro(sensor="PZ-02", timestamp="2026-09-30T09:00:00-03:00"),
            registro(sensor="PZ-01", timestamp="2026-09-30T10:00:00-03:00"),
            registro(sensor="PZ-01", timestamp="2026-09-30T09:00:00-03:00"),
        ]
    )
    assert [(m.sensor, m.timestamp.hour) for m in r.medicoes] == [
        ("PZ-01", 9),
        ("PZ-01", 10),
        ("PZ-02", 9),
    ]


def test_detectar_lacunas():
    horas = [0, 1, 2, 6, 7]
    r = validar([registro(timestamp=f"2026-09-30T{h:02d}:00:00-03:00") for h in horas])
    lacunas = detectar_lacunas(r.medicoes, {"PZ-01": timedelta(hours=1)})
    [lac] = lacunas
    assert (lac.inicio.hour, lac.fim.hour) == (2, 6)
    assert lac.duracao == timedelta(hours=4)


def test_lacunas_ignora_sensor_sem_frequencia():
    r = validar([registro(timestamp="2026-09-30T00:00:00-03:00"), registro(timestamp="2026-09-30T09:00:00-03:00")])
    assert detectar_lacunas(r.medicoes, {}) == []


def test_desempenho_rnf01():
    """RNF-01: 500 medições bem abaixo de 30 s (aqui, validação isolada < 1 s)."""
    import time

    base = datetime(2026, 9, 1, tzinfo=BRT)
    lote = [
        registro(sensor=f"PZ-{i % 10:02d}", timestamp=(base + timedelta(minutes=i)).isoformat())
        for i in range(500)
    ]
    inicio = time.perf_counter()
    r = validar(lote)
    assert len(r.medicoes) == 500
    assert time.perf_counter() - inicio < 1.0
