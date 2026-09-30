"""M2 – Monitoramento: limites de alerta, taxa de variação, anomalias e severidade (RF-04, RF-06)."""

from .avaliacao import ResultadoMonitoramento, SituacaoSensor, avaliar
from .modelo import (
    Alerta,
    Categoria,
    ConfigMonitoramento,
    Direcao,
    DirecaoTaxa,
    LimitesAlerta,
    Niveis,
    ParametrosAnomalia,
    ParametrosTravado,
    RegrasSensor,
    TaxaVariacao,
    TipoAlerta,
)

__all__ = [
    "Alerta",
    "Categoria",
    "ConfigMonitoramento",
    "Direcao",
    "DirecaoTaxa",
    "LimitesAlerta",
    "Niveis",
    "ParametrosAnomalia",
    "ParametrosTravado",
    "RegrasSensor",
    "ResultadoMonitoramento",
    "SituacaoSensor",
    "TaxaVariacao",
    "TipoAlerta",
    "avaliar",
]
