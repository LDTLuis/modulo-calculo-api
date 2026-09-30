from datetime import timedelta, timezone

import pytest

from damiq_calc.adapters.configuracao import Configuracao, ler_configuracao
from damiq_calc.adapters.contrato import processar
from damiq_calc.adapters.leitura import ErroContrato
from damiq_calc.medicoes import TipoMedicao

CONFIG_CENTRAL = {
    "versao": "2026-09-30.3",
    "fuso_padrao": "-03:00",
    "medicoes": {"tolerancia_futuro_s": 60, "fator_tolerancia_lacuna": 2},
    "padroes_por_tipo": {
        "Pressão": {"faixa": {"min": 0, "max": 10, "unidade": "bar"}, "frequencia_esperada_s": 3600},
        "vazao": {"faixa": {"min": 0, "max": 50, "unidade": "L/s"}},
    },
    "sensores": {
        "PZ-01": {"tipo": "pressao", "faixa": {"min": 0, "max": 20, "unidade": "mca"}},
        "RN-01": {"tipo": "nivel", "frequencia_esperada_s": 900},
    },
}


def test_sem_configuracao_usa_padroes_do_motor():
    config = ler_configuracao({})
    assert config == Configuracao()
    assert config.versao is None


def test_le_configuracao_completa():
    config = ler_configuracao({"configuracao": CONFIG_CENTRAL})
    assert config.versao == "2026-09-30.3"
    assert config.fuso_padrao == timezone(timedelta(hours=-3))
    assert config.tolerancia_futuro == timedelta(seconds=60)
    assert config.fator_tolerancia_lacuna == 2
    # faixas convertidas para a unidade canônica do tipo
    assert config.faixas_por_tipo[TipoMedicao.PRESSAO] == pytest.approx((0.0, 1000.0))
    assert config.faixas_por_tipo[TipoMedicao.VAZAO] == pytest.approx((0.0, 0.05))
    assert config.sensores["PZ-01"].faixa == pytest.approx((0.0, 196.2))
    assert config.sensores["PZ-01"].tipo is TipoMedicao.PRESSAO


def test_frequencia_do_sensor_cai_no_padrao_do_tipo():
    config = ler_configuracao({"configuracao": CONFIG_CENTRAL})
    assert config.frequencia_do_sensor("RN-01", TipoMedicao.NIVEL) == timedelta(minutes=15)
    assert config.frequencia_do_sensor("PZ-01", TipoMedicao.PRESSAO) == timedelta(hours=1)
    assert config.frequencia_do_sensor("PZ-99", TipoMedicao.VAZAO) is None


def test_faixa_sem_unidade_usa_canonica():
    config = ler_configuracao(
        {"configuracao": {"versao": 1, "sensores": {"S": {"tipo": "nivel", "faixa": {"max": 760}}}}}
    )
    assert config.sensores["S"].faixa == (None, 760.0)


@pytest.mark.parametrize(
    "configuracao",
    [
        [],
        {},  # versão obrigatória
        {"versao": True},
        {"versao": 1, "fuso_padrao": "America/Sao_Paulo"},
        {"versao": 1, "medicoes": {"tolerancia_futuro_s": -1}},
        {"versao": 1, "medicoes": {"fator_tolerancia_lacuna": 0.5}},
        {"versao": 1, "padroes_por_tipo": {"temperatura": {}}},
        {"versao": 1, "sensores": {"S": {"faixa": {"max": 1}}}},  # tipo obrigatório
        {"versao": 1, "sensores": {"S": {"tipo": "nivel", "faixa": {}}}},
        {"versao": 1, "sensores": {"S": {"tipo": "nivel", "faixa": {"min": "0"}}}},
        {"versao": 1, "sensores": {"S": {"tipo": "nivel", "faixa": {"min": 5, "max": 1}}}},
        {"versao": 1, "sensores": {"S": {"tipo": "nivel", "faixa": {"max": 1, "unidade": "kPa"}}}},
        {"versao": 1, "sensores": {"S": {"tipo": "nivel", "faixa": {"max": 1, "unidade": "pés"}}}},
        {"versao": 1, "sensores": {"S": {"tipo": "nivel", "frequencia_esperada_s": 0}}},
    ],
)
def test_configuracao_invalida(configuracao):
    with pytest.raises(ErroContrato):
        ler_configuracao({"configuracao": configuracao})


def test_processar_lote_aplica_configuracao():
    resp = processar(
        {
            "versao_contrato": "1.0",
            "operacao": "processar_lote",
            "configuracao": CONFIG_CENTRAL,
            "opcoes": {"agora": "2026-09-30T12:00:00-03:00"},
            "medicoes": [
                # 25 mca = 245 kPa > faixa do sensor (20 mca)
                {"sensor": "PZ-01", "tipo": "pressao", "timestamp": "2026-09-30T08:00:00", "valor": 25, "unidade": "mca"},
                # sem faixa própria: usa padrão do tipo (0–50 L/s)
                {"sensor": "MV-01", "tipo": "vazao", "timestamp": "2026-09-30T08:00:00", "valor": 60, "unidade": "L/s"},
                # sensor cadastrado como nível
                {"sensor": "RN-01", "tipo": "pressao", "timestamp": "2026-09-30T08:00:00", "valor": 1, "unidade": "kPa"},
                # 11:59 + 60 s de tolerância: aceita; 12:02: futuro
                {"sensor": "RN-01", "tipo": "nivel", "timestamp": "2026-09-30T11:59:00", "valor": 749, "unidade": "m"},
                {"sensor": "RN-01", "tipo": "nivel", "timestamp": "2026-09-30T12:02:00", "valor": 749, "unidade": "m"},
            ],
        }
    )
    assert resp["versao_config"] == "2026-09-30.3"
    flags = {m["sensor"]: m["flags"] for m in resp["medicoes"]}
    assert flags == {
        "MV-01": ["FORA_FAIXA_PLAUSIVEL"],
        "PZ-01": ["FORA_FAIXA_PLAUSIVEL"],
        "RN-01": [],
    }
    assert [(r["indice"], r["codigo"]) for r in resp["rejeicoes"]] == [
        (2, "TIPO_DIVERGENTE"),
        (4, "TIMESTAMP_FUTURO"),
    ]


def test_lacuna_usa_fator_e_frequencia_da_configuracao():
    base = {"sensor": "RN-01", "tipo": "nivel", "valor": 749, "unidade": "m"}
    resp = processar(
        {
            "versao_contrato": "1.0",
            "operacao": "processar_lote",
            "configuracao": CONFIG_CENTRAL,  # RN-01: 15 min, fator 2 → lacuna se > 30 min
            "opcoes": {"agora": "2026-09-30T12:00:00-03:00"},
            "medicoes": [
                {**base, "timestamp": "2026-09-30T08:00:00"},
                {**base, "timestamp": "2026-09-30T08:30:00"},
                {**base, "timestamp": "2026-09-30T09:01:00"},
            ],
        }
    )
    assert [lac["inicio"] for lac in resp["lacunas"]] == ["2026-09-30T08:30:00-03:00"]


# --- M2: regras de monitoramento --------------------------------------------------------

from damiq_calc.monitoramento import DirecaoTaxa, Niveis  # noqa: E402

CONFIG_M2 = {
    "versao": 13,
    "monitoramento": {
        "anomalia": {"ativo": False},
        "sensor_travado": {"leituras_consecutivas": 4},
    },
    "sensores": {
        "PZ-01": {
            "tipo": "pressao",
            "limites_alerta": {"unidade": "mca", "acima": {"aviso": 18, "alerta": 22, "critico": 26}},
        },
        "RN-01": {
            "tipo": "nivel",
            "limites_alerta": {"abaixo": {"aviso": 745, "critico": 740}},
            "taxa_variacao": {"unidade": "cm", "intervalo_s": 3600, "direcao": "descida", "aviso": 20, "alerta": 50},
        },
    },
}


def test_le_regras_de_monitoramento():
    m = ler_configuracao({"configuracao": CONFIG_M2}).monitoramento
    assert m.anomalia.ativo is False
    assert m.travado.leituras_consecutivas == 4
    assert m.sensores["PZ-01"].limites.acima == Niveis(
        aviso=pytest.approx(176.58), alerta=pytest.approx(215.82), critico=pytest.approx(255.06)
    )
    rn = m.sensores["RN-01"]
    assert rn.limites.abaixo == Niveis(aviso=745.0, critico=740.0)
    assert rn.taxa.niveis == Niveis(aviso=pytest.approx(0.2), alerta=pytest.approx(0.5))
    assert rn.taxa.direcao is DirecaoTaxa.DESCIDA
    assert rn.taxa.intervalo == timedelta(hours=1)


@pytest.mark.parametrize(
    "sensor",
    [
        {"tipo": "pressao", "limites_alerta": {}},
        {"tipo": "pressao", "limites_alerta": {"acima": {}}},
        {"tipo": "pressao", "limites_alerta": {"acima": {"aviso": 220, "alerta": 180}}},
        {"tipo": "nivel", "limites_alerta": {"abaixo": {"aviso": 740, "critico": 745}}},
        {"tipo": "pressao", "limites_alerta": {"unidade": "m", "acima": {"aviso": 1}}},
        {"tipo": "pressao", "limites_alerta": {"acima": {"aviso": "180"}}},
        {"tipo": "nivel", "taxa_variacao": {"aviso": -0.2}},
        {"tipo": "nivel", "taxa_variacao": {"aviso": 0.2, "direcao": "lateral"}},
        {"tipo": "nivel", "taxa_variacao": {"aviso": 0.2, "intervalo_s": 0}},
    ],
)
def test_regras_de_sensor_invalidas(sensor):
    with pytest.raises(ErroContrato):
        ler_configuracao({"configuracao": {"versao": 1, "sensores": {"S": sensor}}})


@pytest.mark.parametrize(
    "monitoramento",
    [
        {"anomalia": {"ativo": "sim"}},
        {"anomalia": {"janela_leituras": 5, "minimo_leituras": 10}},
        {"anomalia": {"limiar_z": 0}},
        {"sensor_travado": {"leituras_consecutivas": 1}},
    ],
)
def test_parametros_de_monitoramento_invalidos(monitoramento):
    with pytest.raises(ErroContrato):
        ler_configuracao({"configuracao": {"versao": 1, "monitoramento": monitoramento}})


def test_processar_lote_gera_alertas_de_ponta_a_ponta():
    def leitura(sensor, tipo, hora, valor, unidade):
        return {"sensor": sensor, "tipo": tipo, "timestamp": f"2026-09-29T{hora:02d}:00:00", "valor": valor, "unidade": unidade}

    resp = processar(
        {
            "versao_contrato": "1.0",
            "operacao": "processar_lote",
            "configuracao": CONFIG_M2,
            "opcoes": {"agora": "2026-09-30T12:00:00-03:00"},
            "historico": [leitura("RN-01", "nivel", 0, 749.9, "m")],
            "medicoes": [
                leitura("PZ-01", "pressao", 1, 150, "kPa"),
                leitura("PZ-01", "pressao", 2, 2.3, "bar"),  # 230 kPa ≥ alerta (215,82)
                leitura("PZ-01", "pressao", 3, 2.4, "bar"),
                leitura("RN-01", "nivel", 1, 749.2, "m"),  # -0,7 m/h: alerta de rebaixamento
            ],
        }
    )
    assert resp["versao_config"] == 13
    assert resp["resumo"]["historico"] == {"recebidas": 1, "validas": 1, "rejeitadas": 0}
    assert resp["monitoramento"]["status_barragem"] == "ALERTA"
    assert resp["monitoramento"]["sensores"]["PZ-01"]["status_atual"] == "ALERTA"
    assert [(a["sensor"], a["tipo"], a["severidade"], a["leituras"]) for a in resp["alertas"]] == [
        ("PZ-01", "LIMITE", "ALERTA", 2),
        ("RN-01", "TAXA_VARIACAO", "ALERTA", 1),
    ]
    assert resp["alertas"][0]["valor_extremo"] == pytest.approx(240.0)


# --- avisos de campos desconhecidos ---------------------------------------------------------


def test_configuracao_valida_nao_gera_avisos():
    assert ler_configuracao({"configuracao": CONFIG_CENTRAL}).avisos == ()
    assert ler_configuracao({"configuracao": CONFIG_M2}).avisos == ()


def test_campos_desconhecidos_geram_avisos():
    config = ler_configuracao(
        {
            "configuracao": {
                "versao": 1,
                "fuso": "-03:00",  # deveria ser fuso_padrao
                "sensores": {
                    "PZ-01": {
                        "tipo": "pressao",
                        "limite_alerta": {"acima": {"aviso": 1}},  # deveria ser limites_alerta
                        "faixa": {"min": 0, "maximo": 10},  # deveria ser max
                        "cota_instalacao_m": 712.5,  # reservado: sem aviso
                    }
                },
                "monitoramento": {"anomalia": {"limiar": 3}},
                "limites_calculo": {"fs_min_pipping": 2.0, "fs_min_talude": 1.5},
                "classificacao": {"qualquer": "coisa"},  # reservado: sem aviso
            }
        }
    )
    assert sorted(a["campo"] for a in config.avisos) == [
        "configuracao.fuso",
        "configuracao.limites_calculo.fs_min_pipping",
        "configuracao.monitoramento.anomalia.limiar",
        "configuracao.sensores.PZ-01.faixa.maximo",
        "configuracao.sensores.PZ-01.limite_alerta",
    ]
    assert all(a["codigo"] == "CAMPO_DESCONHECIDO" for a in config.avisos)
    # o que foi reconhecido continua valendo
    assert config.limites_calculo["fs_min_talude"] == 1.5
    assert config.sensores["PZ-01"].faixa == (0.0, None)


def test_avisos_voltam_na_resposta():
    resp = processar(
        {
            "versao_contrato": "1.0",
            "operacao": "calcular",
            "calculo": "hidrostatica.pressao",
            "configuracao": {"versao": 2, "limites_calculo": {"fs_min_pipping": 2}},
            "entradas": {"profundidade": 1},
        }
    )
    assert resp["status"] == "OK"
    assert [a["campo"] for a in resp["avisos"]] == ["configuracao.limites_calculo.fs_min_pipping"]
