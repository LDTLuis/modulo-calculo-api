"""Regras de monitoramento e alertas (RF-06)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum

from damiq_calc.core.resultado import Severidade


# Leituras são digitadas/importadas (dias entre leituras): taxa de referência diária.
INTERVALO_TAXA_PADRAO = timedelta(days=1)


class Direcao(StrEnum):
    ACIMA = "acima"
    ABAIXO = "abaixo"


class DirecaoTaxa(StrEnum):
    SUBIDA = "subida"
    DESCIDA = "descida"
    AMBAS = "ambas"


class Categoria(StrEnum):
    SEGURANCA = "SEGURANCA"  # compõe o status da barragem
    QUALIDADE = "QUALIDADE"  # compõe o status dos dados


class TipoAlerta(StrEnum):
    LIMITE = "LIMITE"
    TAXA_VARIACAO = "TAXA_VARIACAO"
    FORA_FAIXA_PLAUSIVEL = "FORA_FAIXA_PLAUSIVEL"
    SENSOR_TRAVADO = "SENSOR_TRAVADO"
    ANOMALIA_ESTATISTICA = "ANOMALIA_ESTATISTICA"

    @property
    def categoria(self) -> Categoria:
        if self in (TipoAlerta.LIMITE, TipoAlerta.TAXA_VARIACAO):
            return Categoria.SEGURANCA
        return Categoria.QUALIDADE


@dataclass(frozen=True, slots=True)
class Niveis:
    """Valores de acionamento de cada severidade, na unidade canônica do tipo."""

    aviso: float | None = None
    alerta: float | None = None
    critico: float | None = None

    def pares(self) -> list[tuple[Severidade, float]]:
        todos = [
            (Severidade.AVISO, self.aviso),
            (Severidade.ALERTA, self.alerta),
            (Severidade.CRITICO, self.critico),
        ]
        return [(s, v) for s, v in todos if v is not None]


@dataclass(frozen=True, slots=True)
class LimitesAlerta:
    acima: Niveis | None = None  # valor ≥ nível aciona
    abaixo: Niveis | None = None  # valor ≤ nível aciona


@dataclass(frozen=True, slots=True)
class TaxaVariacao:
    """Variação máxima em `intervalo` (ex.: 0,5 m por hora no rebaixamento do NA)."""

    niveis: Niveis  # magnitudes positivas
    intervalo: timedelta = INTERVALO_TAXA_PADRAO
    direcao: DirecaoTaxa = DirecaoTaxa.AMBAS


@dataclass(frozen=True, slots=True)
class RegrasSensor:
    limites: LimitesAlerta | None = None
    taxa: TaxaVariacao | None = None


@dataclass(frozen=True, slots=True)
class ParametrosAnomalia:
    """Z-score modificado (Iglewicz & Hoaglin): z = 0,6745·(x − mediana)/MAD."""

    ativo: bool = True
    janela_leituras: int = 24
    minimo_leituras: int = 8
    limiar_z: float = 3.5


@dataclass(frozen=True, slots=True)
class ParametrosTravado:
    # Desligado por padrão: com leitura manual, valores repetidos são comuns e legítimos.
    ativo: bool = False
    leituras_consecutivas: int = 12


@dataclass(frozen=True, slots=True)
class ConfigMonitoramento:
    sensores: dict[str, RegrasSensor] = field(default_factory=dict)
    anomalia: ParametrosAnomalia = ParametrosAnomalia()
    travado: ParametrosTravado = ParametrosTravado()


@dataclass(frozen=True, slots=True)
class Alerta:
    """Episódio: leituras consecutivas de um sensor que dispararam a mesma regra."""

    tipo: TipoAlerta
    sensor: str
    severidade: Severidade
    inicio: datetime
    fim: datetime
    leituras: int
    valor_extremo: float
    unidade: str
    mensagem: str
    limite: float | None = None
    direcao: str | None = None
    leitura_suspeita: bool = False  # há leitura fora da faixa plausível no episódio
    detalhe: dict = field(default_factory=dict)

    @property
    def categoria(self) -> Categoria:
        return self.tipo.categoria

    def para_dict(self) -> dict:
        return {
            "tipo": self.tipo.value,
            "categoria": self.categoria.value,
            "sensor": self.sensor,
            "severidade": self.severidade.name,
            "inicio": self.inicio.isoformat(),
            "fim": self.fim.isoformat(),
            "leituras": self.leituras,
            "valor_extremo": self.valor_extremo,
            "unidade": self.unidade,
            "limite": self.limite,
            "direcao": self.direcao,
            "leitura_suspeita": self.leitura_suspeita,
            "mensagem": self.mensagem,
            "detalhe": self.detalhe,
        }
