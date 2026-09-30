"""Gráficos gerados a partir dos resultados das operações do contrato."""

from __future__ import annotations

import re
from collections.abc import Sequence
from pathlib import Path

from damiq_calc.core.calculo import ResultadoCalculo
from damiq_calc.medicoes.modelo import Medicao
from damiq_calc.monitoramento import ConfigMonitoramento, ResultadoMonitoramento

from .figuras import curva_cota_area_volume, serie_temporal


def _nome_arquivo(texto: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", texto).strip("_") or "sensor"


def graficos_do_lote(
    lote: Sequence[Medicao],
    historico: Sequence[Medicao],
    monitoramento: ResultadoMonitoramento,
    config: ConfigMonitoramento,
    diretorio: Path,
    formato: str,
) -> list[dict]:
    """Uma série temporal por sensor do lote (histórico incluído como contexto visual)."""
    chaves_lote = {(m.sensor, m.timestamp) for m in lote}
    por_sensor: dict[str, list[Medicao]] = {}
    for m in [*lote, *(h for h in historico if (h.sensor, h.timestamp) not in chaves_lote)]:
        por_sensor.setdefault(m.sensor, []).append(m)

    saida = []
    for sensor in monitoramento.sensores:
        regras = config.sensores.get(sensor)
        caminho = serie_temporal(
            por_sensor[sensor],
            diretorio / f"serie_{_nome_arquivo(sensor)}.{formato}",
            limites=regras.limites if regras else None,
        )
        saida.append({"tipo": "serie_temporal", "sensor": sensor, "arquivo": str(caminho)})
    return saida


def _curva_cota_volume(execucao: ResultadoCalculo, diretorio: Path, formato: str) -> list[dict]:
    linhas = execucao.memoria.tabelas[0]["linhas"]  # [cota, área, área média, Δh, Vn]
    acumulado, pontos = 0.0, []
    for cota, area, _, _, vn in linhas:
        acumulado += vn
        pontos.append((cota, area, acumulado))
    caminho = curva_cota_area_volume(pontos, diretorio / f"curva_cota_area_volume.{formato}", titulo="Curva cota–área–volume do reservatório")
    return [{"tipo": "curva_cota_area_volume", "arquivo": str(caminho)}]


GRAFICOS_POR_CALCULO = {
    "hidrologia.curva_cota_volume": _curva_cota_volume,
}


def graficos_do_calculo(execucao: ResultadoCalculo, diretorio: Path, formato: str) -> list[dict]:
    gerar = GRAFICOS_POR_CALCULO.get(execucao.definicao.id)
    return gerar(execucao, diretorio, formato) if gerar else []
