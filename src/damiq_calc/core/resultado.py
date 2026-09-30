"""Modelo de resultado comum a todos os módulos de cálculo."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import IntEnum


class Severidade(IntEnum):
    """Escala de severidade do DAMIQ.

    Mapeamento proposto (a validar): OK ↔ Nível 0; AVISO ↔ Nível 1 / verde;
    ALERTA ↔ Nível 2 / amarelo; CRITICO ↔ Nível 3 / vermelho.
    """

    OK = 0
    AVISO = 1
    ALERTA = 2
    CRITICO = 3


def severidade_maxima(severidades: Iterable[Severidade]) -> Severidade:
    return max(severidades, default=Severidade.OK)


@dataclass(frozen=True, slots=True)
class Resultado:
    calculo: str
    valor: float
    unidade: str
    severidade: Severidade = Severidade.OK
    limite: float | None = None
    premissas: tuple[str, ...] = ()
    fonte: str | None = None
    descricao: str | None = None

    def para_dict(self) -> dict:
        return {
            "calculo": self.calculo,
            "descricao": self.descricao,
            "valor": self.valor,
            "unidade": self.unidade,
            "status": self.severidade.name,
            "limite": self.limite,
            "premissas": list(self.premissas),
            "fonte": self.fonte,
        }
