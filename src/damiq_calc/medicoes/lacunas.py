"""Detecção de lacunas nas séries de medições de cada sensor."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from itertools import groupby

from .modelo import Medicao


@dataclass(frozen=True, slots=True)
class Lacuna:
    sensor: str
    inicio: datetime  # última leitura antes do intervalo
    fim: datetime  # primeira leitura depois do intervalo

    @property
    def duracao(self) -> timedelta:
        return self.fim - self.inicio

    def para_dict(self) -> dict:
        return {
            "sensor": self.sensor,
            "inicio": self.inicio.isoformat(),
            "fim": self.fim.isoformat(),
            "duracao_s": self.duracao.total_seconds(),
        }


def detectar_lacunas(
    medicoes: Iterable[Medicao],
    frequencias: Mapping[str, timedelta],
    *,
    fator_tolerancia: float = 1.5,
) -> list[Lacuna]:
    """Aponta intervalos entre leituras consecutivas maiores que `frequência × tolerância`.

    Sensores sem frequência esperada configurada são ignorados.
    """
    ordenadas = sorted(medicoes, key=lambda m: (m.sensor, m.timestamp))
    lacunas: list[Lacuna] = []
    for sensor, grupo in groupby(ordenadas, key=lambda m: m.sensor):
        frequencia = frequencias.get(sensor)
        if frequencia is None:
            continue
        limite = frequencia * fator_tolerancia
        anterior = None
        for medicao in grupo:
            if anterior is not None and medicao.timestamp - anterior.timestamp > limite:
                lacunas.append(Lacuna(sensor, anterior.timestamp, medicao.timestamp))
            anterior = medicao
    return lacunas
