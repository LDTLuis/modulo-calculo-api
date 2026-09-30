"""Seção `configuracao` do contrato: parâmetros cadastrados na Central de Configurações Web.

A Central é a dona desses valores; o Desktop guarda a última versão recebida (SQLite) e a
repassa ao motor a cada chamada. O motor não persiste nada e devolve `versao` na resposta
para auditoria (RF-12). Especificação: docs/contrato.md.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import timedelta, tzinfo

from damiq_calc.core import unidades
from damiq_calc.core.constantes import FUSO_BRASILIA
from damiq_calc.core.erros import UnidadeDesconhecida
from damiq_calc.medicoes import UNIDADE_CANONICA, ConfigSensor, Faixa, TipoMedicao
from damiq_calc.medicoes.modelo import normalizar_tipo
from damiq_calc.monitoramento import (
    ConfigMonitoramento,
    DirecaoTaxa,
    LimitesAlerta,
    Niveis,
    ParametrosAnomalia,
    ParametrosTravado,
    RegrasSensor,
    TaxaVariacao,
)
from damiq_calc.monitoramento.modelo import INTERVALO_TAXA_PADRAO

from .leitura import ErroContrato, eh_numero, fuso, numero_positivo, objeto

SECAO = "configuracao"


@dataclass(frozen=True, slots=True)
class Configuracao:
    versao: str | int | None = None
    fuso_padrao: tzinfo = FUSO_BRASILIA
    tolerancia_futuro: timedelta = timedelta(minutes=5)
    fator_tolerancia_lacuna: float = 1.5
    faixas_por_tipo: dict[TipoMedicao, Faixa] = field(default_factory=dict)
    frequencias_por_tipo: dict[TipoMedicao, timedelta] = field(default_factory=dict)
    sensores: dict[str, ConfigSensor] = field(default_factory=dict)
    monitoramento: ConfigMonitoramento = ConfigMonitoramento()
    # Critérios dos cálculos (ex.: {"fs_min_piping": 1.5}); nomes em `listar_calculos`.
    limites_calculo: dict[str, float] = field(default_factory=dict)

    def frequencia_do_sensor(self, sensor: str, tipo: TipoMedicao) -> timedelta | None:
        config = self.sensores.get(sensor)
        if config and config.frequencia_esperada:
            return config.frequencia_esperada
        return self.frequencias_por_tipo.get(tipo)


def ler_configuracao(requisicao: Mapping) -> Configuracao:
    """Lê `requisicao["configuracao"]`. Ausente = padrões do motor (sem versão)."""
    if SECAO not in requisicao:
        return Configuracao()
    bruto = objeto(requisicao[SECAO], SECAO)

    versao = bruto.get("versao")
    if isinstance(versao, bool) or not isinstance(versao, (str, int)) or versao == "":
        raise ErroContrato(f"'{SECAO}.versao' é obrigatório (texto ou inteiro)")

    kwargs: dict = {"versao": versao}
    if "fuso_padrao" in bruto:
        kwargs["fuso_padrao"] = fuso(bruto["fuso_padrao"], f"{SECAO}.fuso_padrao")

    medicoes = objeto(bruto.get("medicoes", {}), f"{SECAO}.medicoes")
    if "tolerancia_futuro_s" in medicoes:
        valor = medicoes["tolerancia_futuro_s"]
        if not eh_numero(valor) or valor < 0:
            raise ErroContrato(f"'{SECAO}.medicoes.tolerancia_futuro_s' deve ser ≥ 0")
        kwargs["tolerancia_futuro"] = timedelta(seconds=valor)
    if "fator_tolerancia_lacuna" in medicoes:
        campo = f"{SECAO}.medicoes.fator_tolerancia_lacuna"
        fator = numero_positivo(medicoes["fator_tolerancia_lacuna"], campo)
        if fator < 1:
            raise ErroContrato(f"'{campo}' deve ser ≥ 1")
        kwargs["fator_tolerancia_lacuna"] = fator

    faixas: dict[TipoMedicao, Faixa] = {}
    frequencias: dict[TipoMedicao, timedelta] = {}
    padroes = objeto(bruto.get("padroes_por_tipo", {}), f"{SECAO}.padroes_por_tipo")
    for tipo_bruto, padrao_bruto in padroes.items():
        campo = f"{SECAO}.padroes_por_tipo.{tipo_bruto}"
        tipo = _tipo(tipo_bruto, campo)
        padrao = objeto(padrao_bruto, campo)
        if "faixa" in padrao:
            faixas[tipo] = _faixa(padrao["faixa"], tipo, f"{campo}.faixa")
        if "frequencia_esperada_s" in padrao:
            frequencias[tipo] = _frequencia(padrao["frequencia_esperada_s"], campo)

    sensores: dict[str, ConfigSensor] = {}
    regras: dict[str, RegrasSensor] = {}
    for sensor_id, sensor_bruto in objeto(bruto.get("sensores", {}), f"{SECAO}.sensores").items():
        campo = f"{SECAO}.sensores.{sensor_id}"
        sensor = objeto(sensor_bruto, campo)
        if "tipo" not in sensor:
            raise ErroContrato(f"'{campo}.tipo' é obrigatório")
        tipo = _tipo(sensor["tipo"], f"{campo}.tipo")
        sensores[str(sensor_id)] = ConfigSensor(
            tipo=tipo,
            faixa=_faixa(sensor["faixa"], tipo, f"{campo}.faixa") if "faixa" in sensor else None,
            frequencia_esperada=(
                _frequencia(sensor["frequencia_esperada_s"], campo)
                if "frequencia_esperada_s" in sensor
                else None
            ),
        )
        limites = (
            _limites(sensor["limites_alerta"], tipo, f"{campo}.limites_alerta")
            if "limites_alerta" in sensor
            else None
        )
        taxa = (
            _taxa(sensor["taxa_variacao"], tipo, f"{campo}.taxa_variacao")
            if "taxa_variacao" in sensor
            else None
        )
        if limites or taxa:
            regras[str(sensor_id)] = RegrasSensor(limites=limites, taxa=taxa)

    return Configuracao(
        **kwargs,
        faixas_por_tipo=faixas,
        frequencias_por_tipo=frequencias,
        sensores=sensores,
        monitoramento=_monitoramento(bruto, regras),
        limites_calculo=_limites_calculo(bruto),
    )


def _limites_calculo(bruto: Mapping) -> dict[str, float]:
    campo = f"{SECAO}.limites_calculo"
    return {
        str(nome): numero_positivo(valor, f"{campo}.{nome}")
        for nome, valor in objeto(bruto.get("limites_calculo", {}), campo).items()
    }


# --- M2: monitoramento -----------------------------------------------------------------


def _monitoramento(bruto: Mapping, regras: dict[str, RegrasSensor]) -> ConfigMonitoramento:
    campo = f"{SECAO}.monitoramento"
    secao = objeto(bruto.get("monitoramento", {}), campo)

    anomalia = ParametrosAnomalia()
    if "anomalia" in secao:
        a = objeto(secao["anomalia"], f"{campo}.anomalia")
        janela = _inteiro(a.get("janela_leituras", anomalia.janela_leituras), f"{campo}.anomalia.janela_leituras", 3)
        minimo = _inteiro(a.get("minimo_leituras", anomalia.minimo_leituras), f"{campo}.anomalia.minimo_leituras", 3)
        if minimo > janela:
            raise ErroContrato(f"'{campo}.anomalia.minimo_leituras' não pode exceder 'janela_leituras'")
        anomalia = ParametrosAnomalia(
            ativo=_booleano(a.get("ativo", anomalia.ativo), f"{campo}.anomalia.ativo"),
            janela_leituras=janela,
            minimo_leituras=minimo,
            limiar_z=numero_positivo(a.get("limiar_z", anomalia.limiar_z), f"{campo}.anomalia.limiar_z"),
        )

    travado = ParametrosTravado()
    if "sensor_travado" in secao:
        t = objeto(secao["sensor_travado"], f"{campo}.sensor_travado")
        travado = ParametrosTravado(
            ativo=_booleano(t.get("ativo", travado.ativo), f"{campo}.sensor_travado.ativo"),
            leituras_consecutivas=_inteiro(
                t.get("leituras_consecutivas", travado.leituras_consecutivas),
                f"{campo}.sensor_travado.leituras_consecutivas",
                2,
            ),
        )

    return ConfigMonitoramento(sensores=regras, anomalia=anomalia, travado=travado)


def _limites(bruto: object, tipo: TipoMedicao, campo: str) -> LimitesAlerta:
    """{"unidade", "acima": {aviso, alerta, critico}, "abaixo": {...}}"""
    secao = objeto(bruto, campo)
    converter = _conversor(secao.get("unidade"), tipo, f"{campo}.unidade")
    acima = _niveis(secao["acima"], converter, f"{campo}.acima", crescente=True) if "acima" in secao else None
    abaixo = _niveis(secao["abaixo"], converter, f"{campo}.abaixo", crescente=False) if "abaixo" in secao else None
    if acima is None and abaixo is None:
        raise ErroContrato(f"'{campo}' precisa de 'acima' e/ou 'abaixo'")
    return LimitesAlerta(acima=acima, abaixo=abaixo)


def _taxa(bruto: object, tipo: TipoMedicao, campo: str) -> TaxaVariacao:
    """{"unidade", "intervalo_s", "direcao", "aviso", "alerta", "critico"} (magnitudes > 0)."""
    secao = objeto(bruto, campo)
    converter = _conversor(secao.get("unidade"), tipo, f"{campo}.unidade")
    niveis = _niveis(secao, converter, campo, crescente=True)
    if any(v <= 0 for _, v in niveis.pares()):
        raise ErroContrato(f"'{campo}': os níveis de taxa devem ser positivos")
    direcao = secao.get("direcao", DirecaoTaxa.AMBAS.value)
    try:
        direcao = DirecaoTaxa(direcao)
    except ValueError:
        validas = ", ".join(d.value for d in DirecaoTaxa)
        raise ErroContrato(f"'{campo}.direcao' inválida: {direcao!r} (esperado: {validas})") from None
    intervalo = timedelta(seconds=numero_positivo(secao.get("intervalo_s", INTERVALO_TAXA_PADRAO.total_seconds()), f"{campo}.intervalo_s"))
    return TaxaVariacao(niveis=niveis, intervalo=intervalo, direcao=direcao)


def _niveis(bruto: object, converter, campo: str, *, crescente: bool) -> Niveis:
    secao = objeto(bruto, campo)
    valores = {}
    for nome in ("aviso", "alerta", "critico"):
        valor = secao.get(nome)
        if valor is not None and not eh_numero(valor):
            raise ErroContrato(f"'{campo}.{nome}' deve ser número ou null")
        valores[nome] = converter(valor)
    niveis = Niveis(**valores)
    presentes = [v for _, v in niveis.pares()]
    if not presentes:
        raise ErroContrato(f"'{campo}' precisa de ao menos um nível (aviso, alerta ou critico)")
    if presentes != sorted(presentes, reverse=not crescente):
        ordem = "aviso ≤ alerta ≤ critico" if crescente else "aviso ≥ alerta ≥ critico"
        raise ErroContrato(f"'{campo}': níveis fora de ordem (esperado {ordem})")
    return niveis


def _inteiro(valor: object, campo: str, minimo: int) -> int:
    if isinstance(valor, bool) or not isinstance(valor, int) or valor < minimo:
        raise ErroContrato(f"'{campo}' deve ser inteiro ≥ {minimo}")
    return valor


def _booleano(valor: object, campo: str) -> bool:
    if not isinstance(valor, bool):
        raise ErroContrato(f"'{campo}' deve ser true ou false")
    return valor


def _tipo(bruto: object, campo: str) -> TipoMedicao:
    try:
        return normalizar_tipo(str(bruto))
    except ValueError:
        validos = ", ".join(t.value for t in TipoMedicao)
        raise ErroContrato(f"'{campo}': tipo {bruto!r} inválido (esperado: {validos})") from None


def _frequencia(bruto: object, campo: str) -> timedelta:
    return timedelta(seconds=numero_positivo(bruto, f"{campo}.frequencia_esperada_s"))


def _faixa(bruto: object, tipo: TipoMedicao, campo: str) -> Faixa:
    """{"min": .., "max": .., "unidade": ..} → (min, max) na unidade canônica do tipo."""
    faixa = objeto(bruto, campo)
    minimo, maximo = faixa.get("min"), faixa.get("max")
    for nome, valor in (("min", minimo), ("max", maximo)):
        if valor is not None and not eh_numero(valor):
            raise ErroContrato(f"'{campo}.{nome}' deve ser número ou null")
    if minimo is None and maximo is None:
        raise ErroContrato(f"'{campo}' precisa de 'min' e/ou 'max'")
    if minimo is not None and maximo is not None and minimo > maximo:
        raise ErroContrato(f"'{campo}': min ({minimo}) maior que max ({maximo})")

    converter = _conversor(faixa.get("unidade"), tipo, f"{campo}.unidade")
    return (converter(minimo), converter(maximo))


def _conversor(unidade: object, tipo: TipoMedicao, campo: str):
    """Função que leva valores de `unidade` (ausente = canônica) para a unidade canônica do tipo."""
    canonica = UNIDADE_CANONICA[tipo]
    if unidade is None:
        unidade = canonica
    try:
        if unidades.dimensao(unidade) is not unidades.dimensao(canonica):  # type: ignore[arg-type]
            raise ErroContrato(f"'{campo}': {unidade!r} não serve para {tipo.value} (ex.: {canonica})")
    except UnidadeDesconhecida as e:
        raise ErroContrato(f"'{campo}': {e.mensagem}") from None

    def converter(valor):
        return None if valor is None else float(unidades.converter(valor, unidade, canonica))

    return converter
