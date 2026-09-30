"""Leitura e validação de campos do JSON de entrada."""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import datetime, tzinfo

from damiq_calc.core.erros import ErroValidacao


class ErroContrato(ErroValidacao):
    """Requisição fora do contrato. `campo` aponta o caminho do problema (ex.:
    'configuracao.sensores.PZ-01.faixa'); por convenção, as mensagens começam com o campo
    entre aspas simples, de onde ele é extraído quando não é informado."""

    codigo = "CONTRATO_INVALIDO"

    def __init__(self, mensagem: str, codigo: str | None = None, campo: str | None = None):
        super().__init__(mensagem, codigo)
        if campo is None:
            achado = re.match(r"(?:Campo )?'([^']+)'", mensagem)
            campo = achado.group(1) if achado else None
        self.campo = campo


def objeto(valor: object, campo: str) -> Mapping:
    if not isinstance(valor, Mapping):
        raise ErroContrato(f"Campo '{campo}' deve ser um objeto")
    return valor


def eh_numero(valor: object) -> bool:
    return isinstance(valor, (int, float)) and not isinstance(valor, bool)


def numero_positivo(valor: object, campo: str) -> float:
    if not eh_numero(valor) or valor <= 0:  # type: ignore[operator]
        raise ErroContrato(f"'{campo}' deve ser um número positivo")
    return float(valor)  # type: ignore[arg-type]


def fuso(bruto: object, campo: str) -> tzinfo:
    """Aceita offsets ISO como '-03:00'."""
    if isinstance(bruto, str):
        try:
            resultado = datetime.fromisoformat(f"2000-01-01T00:00:00{bruto.strip()}").tzinfo
        except ValueError:
            resultado = None
        if resultado is not None:
            return resultado
    raise ErroContrato(f"'{campo}' inválido: {bruto!r} (ex.: '-03:00')")


def datetime_com_fuso(bruto: object, campo: str) -> datetime:
    try:
        valor = datetime.fromisoformat(bruto)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        raise ErroContrato(f"'{campo}' deve ser ISO 8601 com fuso") from None
    if valor.tzinfo is None:
        raise ErroContrato(f"'{campo}' deve informar o fuso (ex.: -03:00)")
    return valor
