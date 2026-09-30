"""Constantes físicas usadas pelo motor."""

from datetime import timedelta, timezone

# Peso específico da água (kN/m³). A apostila BCST usa 10 kN/m³ nos exemplos resolvidos.
GAMA_W_PADRAO = 9.81
GAMA_W_APOSTILA = 10.0

# Fuso aplicado a timestamps sem offset (Brasil sem horário de verão desde 2019).
FUSO_BRASILIA = timezone(timedelta(hours=-3))
