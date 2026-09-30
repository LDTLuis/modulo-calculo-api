"""Catálogo dos cálculos de engenharia: importar um módulo registra seus cálculos."""

from damiq_calc import classificacao, estabilidade, geometria, hidrologia, hidrostatica, percolacao  # noqa: F401
from damiq_calc.core.calculo import REGISTRO, ResultadoCalculo, executar

__all__ = ["REGISTRO", "ResultadoCalculo", "executar"]
