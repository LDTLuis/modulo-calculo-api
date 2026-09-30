"""Catálogo dos cálculos de engenharia: importar um módulo registra seus cálculos."""

from damiq_calc import (  # noqa: F401
    classificacao,
    emergencia,
    estabilidade,
    geometria,
    hidrologia,
    hidrostatica,
    opcionais,
    percolacao,
)
from damiq_calc.core.calculo import REGISTRO, ResultadoCalculo, executar

__all__ = ["REGISTRO", "ResultadoCalculo", "executar"]
