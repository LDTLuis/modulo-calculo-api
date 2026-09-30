"""M10 – gráficos para os relatórios."""

from datetime import datetime, timedelta, timezone

import pytest

from damiq_calc.adapters.contrato import processar
from damiq_calc.adapters.leitura import ErroContrato
from damiq_calc.graficos import curva_cota_area_volume, serie_temporal
from damiq_calc.medicoes.modelo import FlagQualidade, Medicao, TipoMedicao
from damiq_calc.monitoramento import LimitesAlerta, Niveis

PNG = b"\x89PNG\r\n\x1a\n"
BRT = timezone(timedelta(hours=-3))


def medicoes(valores, flags=None):
    t0 = datetime(2026, 9, 1, 8, tzinfo=BRT)
    flags = flags or {}
    return [
        Medicao("PZ-01", TipoMedicao.PRESSAO, t0 + timedelta(days=7 * i), float(v), "kPa", float(v), "kPa", flags.get(i, ()))
        for i, v in enumerate(valores)
    ]


def test_serie_temporal_png(tmp_path):
    caminho = serie_temporal(
        medicoes([150, 170, 190, 230, 210], flags={3: (FlagQualidade.FORA_FAIXA_PLAUSIVEL,)}),
        tmp_path / "sub" / "serie.png",
        limites=LimitesAlerta(acima=Niveis(aviso=180, alerta=220, critico=260)),
    )
    assert caminho.read_bytes().startswith(PNG)


def test_serie_temporal_svg(tmp_path):
    caminho = serie_temporal(medicoes([1, 2, 3]), tmp_path / "serie.svg")
    assert b"<svg" in caminho.read_bytes()[:500]


def test_serie_vazia(tmp_path):
    with pytest.raises(ValueError):
        serie_temporal([], tmp_path / "x.png")


def test_curva_cota_area_volume(tmp_path):
    pontos = [(99.5, 0, 0), (100, 980, 245), (101, 1680, 1575), (102, 2048, 3439), (103, 2720, 5823)]
    assert curva_cota_area_volume(pontos, tmp_path / "curva.png").read_bytes().startswith(PNG)


def test_processar_lote_gera_uma_serie_por_sensor(tmp_path):
    def leitura(sensor, dia, valor):
        return {"sensor": sensor, "tipo": "pressao", "timestamp": f"2026-09-{dia:02d}T08:00:00", "valor": valor, "unidade": "kPa"}

    resp = processar(
        {
            "versao_contrato": "1.0",
            "operacao": "processar_lote",
            "configuracao": {"versao": 1, "sensores": {"PZ/01": {"tipo": "pressao", "limites_alerta": {"acima": {"aviso": 180}}}}},
            "opcoes": {"agora": "2026-09-30T12:00:00-03:00", "graficos": {"diretorio": str(tmp_path)}},
            "historico": [leitura("PZ/01", 1, 150)],
            "medicoes": [leitura("PZ/01", 8, 190), leitura("PZ-02", 8, 100)],
        }
    )
    arquivos = {g["sensor"]: g["arquivo"] for g in resp["graficos"]}
    assert set(arquivos) == {"PZ/01", "PZ-02"}
    assert arquivos["PZ/01"].endswith("serie_PZ_01.png")  # nome de arquivo seguro
    for caminho in arquivos.values():
        assert open(caminho, "rb").read(8) == PNG


def test_calcular_curva_cota_volume_com_grafico(tmp_path):
    resp = processar(
        {
            "versao_contrato": "1.0",
            "operacao": "calcular",
            "calculo": "hidrologia.curva_cota_volume",
            "entradas": {"pontos": [{"cota": 99.5, "area": 0}, {"cota": 100, "area": 980}, {"cota": 101, "area": 1680}]},
            "opcoes": {"graficos": {"diretorio": str(tmp_path), "formato": "svg"}},
        }
    )
    [g] = resp["graficos"]
    assert g["tipo"] == "curva_cota_area_volume" and g["arquivo"].endswith(".svg")


def test_calcular_sem_grafico_associado(tmp_path):
    resp = processar(
        {
            "versao_contrato": "1.0",
            "operacao": "calcular",
            "calculo": "hidrostatica.pressao",
            "entradas": {"profundidade": 10},
            "opcoes": {"graficos": {"diretorio": str(tmp_path)}},
        }
    )
    assert resp["graficos"] == []


@pytest.mark.parametrize("graficos", [{}, {"diretorio": ""}, {"diretorio": "x", "formato": "jpg"}, "pasta"])
def test_opcoes_de_grafico_invalidas(graficos):
    with pytest.raises(ErroContrato):
        processar({"versao_contrato": "1.0", "operacao": "processar_lote", "medicoes": [], "opcoes": {"graficos": graficos}})
