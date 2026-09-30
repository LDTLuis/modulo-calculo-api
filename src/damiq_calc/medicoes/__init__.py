"""M1 – Medições: validação, normalização de unidades e detecção de lacunas (RF-03, RF-04)."""

from .lacunas import Lacuna, detectar_lacunas
from .modelo import UNIDADE_CANONICA, Medicao, Rejeicao, TipoMedicao
from .validacao import ConfigSensor, Faixa, ResultadoValidacao, validar_lote

__all__ = [
    "UNIDADE_CANONICA",
    "ConfigSensor",
    "Faixa",
    "Lacuna",
    "Medicao",
    "Rejeicao",
    "ResultadoValidacao",
    "TipoMedicao",
    "detectar_lacunas",
    "validar_lote",
]
