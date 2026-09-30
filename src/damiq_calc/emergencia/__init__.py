"""M9 – Emergência / PAE: nível de resposta e Zona de Autossalvamento (ZAS)."""

from . import calculos  # noqa: F401  (registra os cálculos)
from .niveis import NIVEIS_RESPOSTA, NivelResposta, nivel_de_resposta

__all__ = ["NIVEIS_RESPOSTA", "NivelResposta", "nivel_de_resposta"]
