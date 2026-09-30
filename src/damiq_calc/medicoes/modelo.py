"""Entidades do domínio de medições."""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class TipoMedicao(StrEnum):
    NIVEL = "nivel"
    PRESSAO = "pressao"
    VAZAO = "vazao"
    DESLOCAMENTO = "deslocamento"


# Unidade em que cada tipo é armazenado e calculado.
UNIDADE_CANONICA: dict[TipoMedicao, str] = {
    TipoMedicao.NIVEL: "m",
    TipoMedicao.PRESSAO: "kPa",
    TipoMedicao.VAZAO: "m3/s",
    TipoMedicao.DESLOCAMENTO: "mm",
}


def normalizar_tipo(tipo: str) -> TipoMedicao:
    """Aceita variações como 'Nível', 'PRESSÃO' ou ' vazao '."""
    sem_acento = "".join(
        c for c in unicodedata.normalize("NFKD", tipo) if not unicodedata.combining(c)
    )
    return TipoMedicao(sem_acento.strip().lower())


class CodigoRejeicao(StrEnum):
    REGISTRO_INVALIDO = "REGISTRO_INVALIDO"
    CAMPO_AUSENTE = "CAMPO_AUSENTE"
    SENSOR_INVALIDO = "SENSOR_INVALIDO"
    TIPO_INVALIDO = "TIPO_INVALIDO"
    TIPO_DIVERGENTE = "TIPO_DIVERGENTE"
    TIMESTAMP_INVALIDO = "TIMESTAMP_INVALIDO"
    TIMESTAMP_FUTURO = "TIMESTAMP_FUTURO"
    VALOR_INVALIDO = "VALOR_INVALIDO"
    UNIDADE_DESCONHECIDA = "UNIDADE_DESCONHECIDA"
    UNIDADE_INCOMPATIVEL = "UNIDADE_INCOMPATIVEL"
    DUPLICADA = "DUPLICADA"


class FlagQualidade(StrEnum):
    # Medição mantida, mas fora da faixa plausível: pode ser erro de sensor ou evento real,
    # por isso não é descartada – o monitoramento (M2) decide.
    FORA_FAIXA_PLAUSIVEL = "FORA_FAIXA_PLAUSIVEL"


@dataclass(frozen=True, slots=True)
class Medicao:
    sensor: str
    tipo: TipoMedicao
    timestamp: datetime
    valor: float
    unidade: str
    valor_original: float
    unidade_original: str
    flags: tuple[FlagQualidade, ...] = ()

    def para_dict(self) -> dict:
        return {
            "sensor": self.sensor,
            "tipo": self.tipo.value,
            "timestamp": self.timestamp.isoformat(),
            "valor": self.valor,
            "unidade": self.unidade,
            "valor_original": self.valor_original,
            "unidade_original": self.unidade_original,
            "flags": [f.value for f in self.flags],
        }


@dataclass(frozen=True, slots=True)
class Rejeicao:
    indice: int
    codigo: CodigoRejeicao
    mensagem: str

    def para_dict(self) -> dict:
        return {"indice": self.indice, "codigo": self.codigo.value, "mensagem": self.mensagem}
