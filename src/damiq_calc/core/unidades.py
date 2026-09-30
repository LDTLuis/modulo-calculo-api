"""Conversão de unidades usadas nas medições e nos cálculos.

Cada unidade pertence a uma dimensão e tem um fator para a unidade base da dimensão
(SI, exceto pressão, cuja base é kPa). As funções aceitam escalares ou arrays NumPy.
"""

from __future__ import annotations

import math
import unicodedata
from enum import StrEnum

from .constantes import GAMA_W_PADRAO
from .erros import UnidadeDesconhecida, UnidadeIncompativel


class Dimensao(StrEnum):
    COMPRIMENTO = "comprimento"
    PRESSAO = "pressao"
    VAZAO = "vazao"
    AREA = "area"
    VOLUME = "volume"
    VELOCIDADE = "velocidade"
    PESO_ESPECIFICO = "peso_especifico"
    ANGULO = "angulo"
    FORCA_LINEAR = "forca_linear"
    ADIMENSIONAL = "adimensional"


_D = Dimensao

# chave normalizada -> (dimensão, fator para a base, grafia canônica)
_UNIDADES: dict[str, tuple[Dimensao, float, str]] = {
    "m": (_D.COMPRIMENTO, 1.0, "m"),
    "cm": (_D.COMPRIMENTO, 1e-2, "cm"),
    "mm": (_D.COMPRIMENTO, 1e-3, "mm"),
    "km": (_D.COMPRIMENTO, 1e3, "km"),
    "kpa": (_D.PRESSAO, 1.0, "kPa"),
    "pa": (_D.PRESSAO, 1e-3, "Pa"),
    "mpa": (_D.PRESSAO, 1e3, "MPa"),
    "bar": (_D.PRESSAO, 100.0, "bar"),
    "psi": (_D.PRESSAO, 6.894757293168361, "psi"),
    # metro de coluna d'água: 1 mca = γw kPa (premissa: γw padrão do motor)
    "mca": (_D.PRESSAO, GAMA_W_PADRAO, "mca"),
    "m3/s": (_D.VAZAO, 1.0, "m3/s"),
    "m3/h": (_D.VAZAO, 1 / 3600, "m3/h"),
    "l/s": (_D.VAZAO, 1e-3, "L/s"),
    "l/min": (_D.VAZAO, 1e-3 / 60, "L/min"),
    "l/h": (_D.VAZAO, 1e-3 / 3600, "L/h"),
    "m2": (_D.AREA, 1.0, "m2"),
    "ha": (_D.AREA, 1e4, "ha"),
    "km2": (_D.AREA, 1e6, "km2"),
    "m3": (_D.VOLUME, 1.0, "m3"),
    "l": (_D.VOLUME, 1e-3, "L"),
    "hm3": (_D.VOLUME, 1e6, "hm3"),
    "m/s": (_D.VELOCIDADE, 1.0, "m/s"),
    "cm/s": (_D.VELOCIDADE, 1e-2, "cm/s"),
    "kn/m3": (_D.PESO_ESPECIFICO, 1.0, "kN/m3"),
    # força por metro de barragem (1 tf = 9,80665 kN)
    "kn/m": (_D.FORCA_LINEAR, 1.0, "kN/m"),
    "tf/m": (_D.FORCA_LINEAR, 9.80665, "tf/m"),
    "grau": (_D.ANGULO, 1.0, "grau"),
    "rad": (_D.ANGULO, 180 / math.pi, "rad"),
    "-": (_D.ADIMENSIONAL, 1.0, "-"),
    "%": (_D.ADIMENSIONAL, 1e-2, "%"),
}

_ALIASES = {
    "mh2o": "mca",
    "m.c.a.": "mca",
    "m.c.a": "mca",
    "lps": "l/s",
    "m3/seg": "m3/s",
    "°": "grau",
    "graus": "grau",
    "deg": "grau",
}


def normalizar_unidade(unidade: str) -> str:
    """Retorna a chave interna da unidade ('m³/s', 'M3/S' e 'm3/s' → 'm3/s')."""
    if not isinstance(unidade, str):
        raise UnidadeDesconhecida(f"Unidade deve ser texto, recebido {unidade!r}")
    # NFKC converte sobrescritos: 'm³' -> 'm3', 'km²' -> 'km2'
    chave = unicodedata.normalize("NFKC", unidade).strip().lower().replace(" ", "")
    chave = _ALIASES.get(chave, chave)
    if chave not in _UNIDADES:
        raise UnidadeDesconhecida(f"Unidade desconhecida: {unidade!r}")
    return chave


def dimensao(unidade: str) -> Dimensao:
    return _UNIDADES[normalizar_unidade(unidade)][0]


def nome_canonico(unidade: str) -> str:
    return _UNIDADES[normalizar_unidade(unidade)][2]


def unidades_da_dimensao(dim: Dimensao) -> list[str]:
    """Grafias canônicas aceitas para a dimensão (para listas de seleção nas telas)."""
    return [nome for d, _, nome in _UNIDADES.values() if d is dim]


def converter(valor, de: str, para: str):
    """Converte `valor` da unidade `de` para `para`, que devem ter a mesma dimensão."""
    dim_de, fator_de, _ = _UNIDADES[normalizar_unidade(de)]
    dim_para, fator_para, _ = _UNIDADES[normalizar_unidade(para)]
    if dim_de is not dim_para:
        raise UnidadeIncompativel(
            f"Não é possível converter {de!r} ({dim_de}) para {para!r} ({dim_para})"
        )
    return valor * (fator_de / fator_para)
