"""Regras de avaliação por leitura: limites, taxa de variação, z-score e sensor travado."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import timedelta
from statistics import median

from damiq_calc.core.resultado import Severidade

from .modelo import Direcao, DirecaoTaxa, LimitesAlerta, Niveis, TaxaVariacao

# Constante do z-score modificado (Iglewicz & Hoaglin, 1993).
_K_MAD = 0.6745


def classificar_limite(
    valor: float, limites: LimitesAlerta
) -> tuple[Severidade, float | None, Direcao | None]:
    """Maior severidade atingida (valor ≥ nível acima, ou ≤ nível abaixo)."""
    melhor: tuple[Severidade, float | None, Direcao | None] = (Severidade.OK, None, None)
    for direcao, niveis in ((Direcao.ACIMA, limites.acima), (Direcao.ABAIXO, limites.abaixo)):
        if niveis is None:
            continue
        for severidade, nivel in niveis.pares():
            atingiu = valor >= nivel if direcao is Direcao.ACIMA else valor <= nivel
            if atingiu and severidade > melhor[0]:
                melhor = (severidade, nivel, direcao)
    return melhor


def taxa_no_intervalo(
    valor_anterior: float, valor: float, dt: timedelta, intervalo: timedelta
) -> float:
    """Variação extrapolada para o intervalo de referência (com sinal)."""
    return (valor - valor_anterior) / dt.total_seconds() * intervalo.total_seconds()


def classificar_taxa(taxa: float, regra: TaxaVariacao) -> tuple[Severidade, float | None]:
    if regra.direcao is DirecaoTaxa.SUBIDA:
        magnitude = taxa
    elif regra.direcao is DirecaoTaxa.DESCIDA:
        magnitude = -taxa
    else:
        magnitude = abs(taxa)
    return _maior_atingido(magnitude, regra.niveis)


def z_modificado(valor: float, janela: Sequence[float]) -> float | None:
    """Z-score robusto do valor frente à janela; None se a janela não tem dispersão (MAD = 0)."""
    mediana = median(janela)
    mad = median(abs(x - mediana) for x in janela)
    if mad == 0:
        return None
    return _K_MAD * (valor - mediana) / mad


def sequencias_iguais(valores: Sequence[float], minimo: int) -> list[tuple[int, int]]:
    """Intervalos [início, fim] (inclusivos) com pelo menos `minimo` valores idênticos seguidos."""
    sequencias = []
    inicio = 0
    for i in range(1, len(valores) + 1):
        if i == len(valores) or valores[i] != valores[inicio]:
            if i - inicio >= minimo:
                sequencias.append((inicio, i - 1))
            inicio = i
    return sequencias


def _maior_atingido(magnitude: float, niveis: Niveis) -> tuple[Severidade, float | None]:
    melhor: tuple[Severidade, float | None] = (Severidade.OK, None)
    for severidade, nivel in niveis.pares():
        if magnitude >= nivel and severidade > melhor[0]:
            melhor = (severidade, nivel)
    return melhor
