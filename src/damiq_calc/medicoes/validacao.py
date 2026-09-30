"""Validação e normalização de lotes de medições (RF-03, RF-04)."""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta, tzinfo

from damiq_calc.core import unidades
from damiq_calc.core.constantes import FUSO_BRASILIA
from damiq_calc.core.erros import UnidadeDesconhecida

from .modelo import (
    UNIDADE_CANONICA,
    CodigoRejeicao,
    FlagQualidade,
    Medicao,
    Rejeicao,
    TipoMedicao,
    normalizar_tipo,
)

CAMPOS_OBRIGATORIOS = ("sensor", "tipo", "timestamp", "valor", "unidade")

# (mínimo, máximo) na unidade canônica do tipo; None = aberto.
Faixa = tuple[float | None, float | None]

# Faixas embutidas, usadas só quando a Central não envia padrão para o tipo.
FAIXAS_PADRAO: dict[TipoMedicao, Faixa] = {
    TipoMedicao.VAZAO: (0.0, None),
}


@dataclass(frozen=True, slots=True)
class ConfigSensor:
    tipo: TipoMedicao | None = None  # tipo cadastrado; leituras de outro tipo são rejeitadas
    faixa: Faixa | None = None
    frequencia_esperada: timedelta | None = None


@dataclass(slots=True)
class ResultadoValidacao:
    medicoes: list[Medicao] = field(default_factory=list)
    rejeicoes: list[Rejeicao] = field(default_factory=list)


class _Rejeitado(Exception):
    def __init__(self, codigo: CodigoRejeicao, mensagem: str):
        self.codigo = codigo
        self.mensagem = mensagem


def validar_lote(
    registros: Iterable[object],
    *,
    sensores: Mapping[str, ConfigSensor] | None = None,
    faixas_por_tipo: Mapping[TipoMedicao, Faixa] | None = None,
    agora: datetime | None = None,
    fuso_padrao: tzinfo = FUSO_BRASILIA,
    tolerancia_futuro: timedelta = timedelta(minutes=5),
) -> ResultadoValidacao:
    """Valida e normaliza um lote.

    Registros inválidos viram `Rejeicao` (com o índice no lote); os válidos são convertidos
    para a unidade canônica do tipo e retornados ordenados por sensor e timestamp.
    A faixa plausível vem do sensor; na falta dela, do padrão do tipo.
    """
    sensores = sensores or {}
    faixas = {**FAIXAS_PADRAO, **(faixas_por_tipo or {})}
    limite_futuro = (agora or datetime.now(fuso_padrao)) + tolerancia_futuro
    resultado = ResultadoValidacao()
    vistos: set[tuple[str, datetime]] = set()

    for indice, registro in enumerate(registros):
        try:
            medicao = _validar_registro(registro, sensores, faixas, fuso_padrao, limite_futuro)
            chave = (medicao.sensor, medicao.timestamp)
            if chave in vistos:
                raise _Rejeitado(
                    CodigoRejeicao.DUPLICADA,
                    f"Já existe medição do sensor {medicao.sensor!r} em {medicao.timestamp.isoformat()}",
                )
            vistos.add(chave)
            resultado.medicoes.append(medicao)
        except _Rejeitado as r:
            resultado.rejeicoes.append(Rejeicao(indice, r.codigo, r.mensagem))

    resultado.medicoes.sort(key=lambda m: (m.sensor, m.timestamp))
    return resultado


def _validar_registro(
    registro: object,
    sensores: Mapping[str, ConfigSensor],
    faixas_por_tipo: Mapping[TipoMedicao, Faixa],
    fuso_padrao: tzinfo,
    limite_futuro: datetime,
) -> Medicao:
    if not isinstance(registro, Mapping):
        raise _Rejeitado(CodigoRejeicao.REGISTRO_INVALIDO, "Registro deve ser um objeto")

    ausentes = [c for c in CAMPOS_OBRIGATORIOS if registro.get(c) in (None, "")]
    if ausentes:
        raise _Rejeitado(CodigoRejeicao.CAMPO_AUSENTE, f"Campos ausentes: {', '.join(ausentes)}")

    sensor = _ler_sensor(registro["sensor"])
    tipo = _ler_tipo(registro["tipo"])
    config = sensores.get(sensor)
    if config and config.tipo and config.tipo is not tipo:
        raise _Rejeitado(
            CodigoRejeicao.TIPO_DIVERGENTE,
            f"Sensor {sensor!r} está cadastrado como {config.tipo.value}, leitura veio como {tipo.value}",
        )
    timestamp = _ler_timestamp(registro["timestamp"], fuso_padrao)
    if timestamp > limite_futuro:
        raise _Rejeitado(
            CodigoRejeicao.TIMESTAMP_FUTURO, f"Timestamp no futuro: {timestamp.isoformat()}"
        )
    valor_original = _ler_valor(registro["valor"])
    unidade_original = registro["unidade"]
    valor = _converter_para_canonica(valor_original, unidade_original, tipo)

    faixa = config.faixa if config and config.faixa else faixas_por_tipo.get(tipo)
    flags = (FlagQualidade.FORA_FAIXA_PLAUSIVEL,) if faixa and not _dentro(valor, faixa) else ()

    return Medicao(
        sensor=sensor,
        tipo=tipo,
        timestamp=timestamp,
        valor=valor,
        unidade=UNIDADE_CANONICA[tipo],
        valor_original=valor_original,
        unidade_original=str(unidade_original),
        flags=flags,
    )


def _ler_sensor(bruto: object) -> str:
    if isinstance(bruto, bool) or not isinstance(bruto, (str, int)) or not str(bruto).strip():
        raise _Rejeitado(CodigoRejeicao.SENSOR_INVALIDO, f"Sensor inválido: {bruto!r}")
    return str(bruto).strip()


def _ler_tipo(bruto: object) -> TipoMedicao:
    try:
        return normalizar_tipo(str(bruto))
    except ValueError:
        validos = ", ".join(t.value for t in TipoMedicao)
        raise _Rejeitado(
            CodigoRejeicao.TIPO_INVALIDO, f"Tipo {bruto!r} inválido (esperado: {validos})"
        ) from None


def _ler_timestamp(bruto: object, fuso_padrao: tzinfo) -> datetime:
    if isinstance(bruto, datetime):
        ts = bruto
    elif isinstance(bruto, str):
        try:
            ts = datetime.fromisoformat(bruto.strip())
        except ValueError:
            raise _Rejeitado(
                CodigoRejeicao.TIMESTAMP_INVALIDO,
                f"Timestamp {bruto!r} não está em ISO 8601",
            ) from None
    else:
        raise _Rejeitado(CodigoRejeicao.TIMESTAMP_INVALIDO, f"Timestamp inválido: {bruto!r}")
    return ts if ts.tzinfo else ts.replace(tzinfo=fuso_padrao)


def _ler_valor(bruto: object) -> float:
    if isinstance(bruto, bool):
        raise _Rejeitado(CodigoRejeicao.VALOR_INVALIDO, f"Valor inválido: {bruto!r}")
    if isinstance(bruto, str):
        texto = bruto.strip()
        # Planilhas pt-BR: "12,5" -> 12.5 (sem separador de milhar)
        if texto.count(",") == 1 and "." not in texto:
            texto = texto.replace(",", ".")
        bruto = texto
    try:
        valor = float(bruto)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        raise _Rejeitado(CodigoRejeicao.VALOR_INVALIDO, f"Valor não numérico: {bruto!r}") from None
    if not math.isfinite(valor):
        raise _Rejeitado(CodigoRejeicao.VALOR_INVALIDO, f"Valor não finito: {bruto!r}")
    return valor


def _converter_para_canonica(valor: float, unidade: object, tipo: TipoMedicao) -> float:
    canonica = UNIDADE_CANONICA[tipo]
    try:
        dim = unidades.dimensao(unidade)  # type: ignore[arg-type]
    except UnidadeDesconhecida as e:
        raise _Rejeitado(CodigoRejeicao.UNIDADE_DESCONHECIDA, e.mensagem) from None
    if dim is not unidades.dimensao(canonica):
        raise _Rejeitado(
            CodigoRejeicao.UNIDADE_INCOMPATIVEL,
            f"Unidade {unidade!r} ({dim}) não serve para medição de {tipo.value}",
        )
    return float(unidades.converter(valor, unidade, canonica))  # type: ignore[arg-type]


def _dentro(valor: float, faixa: Faixa) -> bool:
    minimo, maximo = faixa
    return (minimo is None or valor >= minimo) and (maximo is None or valor <= maximo)
