"""Avaliação de um lote de medições: gera alertas por episódio e a situação de cada sensor."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import timedelta

from damiq_calc.core.resultado import Severidade, severidade_maxima
from damiq_calc.medicoes.modelo import FlagQualidade, Medicao, TipoMedicao

from . import regras
from .modelo import Alerta, Categoria, ConfigMonitoramento, RegrasSensor, TipoAlerta


@dataclass(frozen=True, slots=True)
class SituacaoSensor:
    sensor: str
    tipo: TipoMedicao
    ultima: Medicao
    status_atual: Severidade  # limite na última leitura do lote
    status_maximo: Severidade  # pior alerta de segurança no lote

    def para_dict(self) -> dict:
        return {
            "tipo": self.tipo.value,
            "ultima_leitura": {
                "timestamp": self.ultima.timestamp.isoformat(),
                "valor": self.ultima.valor,
                "unidade": self.ultima.unidade,
            },
            "status_atual": self.status_atual.name,
            "status_maximo": self.status_maximo.name,
        }


@dataclass(slots=True)
class ResultadoMonitoramento:
    alertas: list[Alerta] = field(default_factory=list)
    sensores: dict[str, SituacaoSensor] = field(default_factory=dict)

    def status(self, categoria: Categoria) -> Severidade:
        return severidade_maxima(a.severidade for a in self.alertas if a.categoria is categoria)

    @property
    def status_barragem(self) -> Severidade:
        return self.status(Categoria.SEGURANCA)

    @property
    def status_dados(self) -> Severidade:
        return self.status(Categoria.QUALIDADE)


@dataclass(frozen=True, slots=True)
class _Ocorrencia:
    tipo: TipoAlerta
    indice: int  # posição na série do sensor
    severidade: Severidade
    valor: float
    magnitude: float  # critério para escolher o valor extremo do episódio
    limite: float | None = None
    direcao: str | None = None
    detalhe: dict = field(default_factory=dict)


def avaliar(
    lote: Iterable[Medicao],
    config: ConfigMonitoramento,
    historico: Iterable[Medicao] = (),
) -> ResultadoMonitoramento:
    """Aplica as regras às leituras do lote.

    O histórico serve apenas de contexto (taxa de variação, janela estatística, sensor
    travado) e não gera alertas por si só. Leituras do histórico com o mesmo sensor e
    timestamp de uma leitura do lote são descartadas.
    """
    lote = list(lote)
    chaves_lote = {(m.sensor, m.timestamp) for m in lote}
    series: dict[str, list[tuple[Medicao, bool]]] = defaultdict(list)
    for m in historico:
        if (m.sensor, m.timestamp) not in chaves_lote:
            series[m.sensor].append((m, False))
    for m in lote:
        series[m.sensor].append((m, True))

    resultado = ResultadoMonitoramento()
    for sensor in sorted(series):
        serie = sorted(series[sensor], key=lambda par: par[0].timestamp)
        if not any(em_lote for _, em_lote in serie):
            continue
        medicoes = [m for m, _ in serie]
        em_lote = [flag for _, flag in serie]
        regras_sensor = config.sensores.get(sensor, RegrasSensor())

        ocorrencias = _ocorrencias_por_leitura(medicoes, em_lote, regras_sensor, config)
        alertas = _agrupar(sensor, medicoes, ocorrencias, regras_sensor)
        if config.travado.ativo:
            alertas += _travamentos(sensor, medicoes, em_lote, config.travado.leituras_consecutivas)
        alertas.sort(key=lambda a: (a.inicio, a.tipo))
        resultado.alertas += alertas

        ultima = max((m for m, flag in serie if flag), key=lambda m: m.timestamp)
        status_atual = (
            regras.classificar_limite(ultima.valor, regras_sensor.limites)[0]
            if regras_sensor.limites
            else Severidade.OK
        )
        resultado.sensores[sensor] = SituacaoSensor(
            sensor=sensor,
            tipo=ultima.tipo,
            ultima=ultima,
            status_atual=status_atual,
            status_maximo=severidade_maxima(
                a.severidade for a in alertas if a.categoria is Categoria.SEGURANCA
            ),
        )
    return resultado


def _ocorrencias_por_leitura(
    medicoes: list[Medicao],
    em_lote: list[bool],
    regras_sensor: RegrasSensor,
    config: ConfigMonitoramento,
) -> list[_Ocorrencia]:
    ocorrencias = []
    anomalia = config.anomalia
    for i, m in enumerate(medicoes):
        if not em_lote[i]:
            continue

        if regras_sensor.limites:
            sev, limite, direcao = regras.classificar_limite(m.valor, regras_sensor.limites)
            if sev > Severidade.OK:
                ocorrencias.append(
                    _Ocorrencia(
                        TipoAlerta.LIMITE, i, sev, m.valor,
                        magnitude=m.valor if direcao == "acima" else -m.valor,
                        limite=limite, direcao=direcao,
                    )
                )

        if FlagQualidade.FORA_FAIXA_PLAUSIVEL in m.flags:
            ocorrencias.append(
                _Ocorrencia(TipoAlerta.FORA_FAIXA_PLAUSIVEL, i, Severidade.AVISO, m.valor, abs(m.valor))
            )

        if regras_sensor.taxa and i > 0:
            regra = regras_sensor.taxa
            anterior = medicoes[i - 1]
            taxa = regras.taxa_no_intervalo(
                anterior.valor, m.valor, m.timestamp - anterior.timestamp, regra.intervalo
            )
            sev, limite = regras.classificar_taxa(taxa, regra)
            if sev > Severidade.OK:
                ocorrencias.append(
                    _Ocorrencia(
                        TipoAlerta.TAXA_VARIACAO, i, sev, taxa, abs(taxa), limite=limite,
                        direcao="subida" if taxa > 0 else "descida",
                    )
                )

        if anomalia.ativo and i >= anomalia.minimo_leituras:
            janela = [x.valor for x in medicoes[max(0, i - anomalia.janela_leituras) : i]]
            z = regras.z_modificado(m.valor, janela)
            if z is not None and abs(z) > anomalia.limiar_z:
                ocorrencias.append(
                    _Ocorrencia(
                        TipoAlerta.ANOMALIA_ESTATISTICA, i, Severidade.AVISO, m.valor, abs(z),
                        limite=anomalia.limiar_z,
                        detalhe={"z": round(z, 3), "janela_leituras": len(janela)},
                    )
                )
    return ocorrencias


def _agrupar(
    sensor: str,
    medicoes: list[Medicao],
    ocorrencias: list[_Ocorrencia],
    regras_sensor: RegrasSensor,
) -> list[Alerta]:
    """Junta ocorrências da mesma regra em leituras consecutivas num único episódio."""
    grupos: list[list[_Ocorrencia]] = []
    for oc in sorted(ocorrencias, key=lambda o: (o.tipo, o.direcao or "", o.indice)):
        ultimo = grupos[-1][-1] if grupos else None
        if (
            ultimo
            and ultimo.tipo is oc.tipo
            and ultimo.direcao == oc.direcao
            and oc.indice == ultimo.indice + 1
        ):
            grupos[-1].append(oc)
        else:
            grupos.append([oc])

    alertas = []
    for grupo in grupos:
        pior = max(grupo, key=lambda o: o.severidade)
        extremo = max(grupo, key=lambda o: o.magnitude)
        primeira, ultima = medicoes[grupo[0].indice], medicoes[grupo[-1].indice]
        unidade = primeira.unidade
        if pior.tipo is TipoAlerta.TAXA_VARIACAO:
            unidade = f"{unidade}/{_rotulo_intervalo(regras_sensor.taxa.intervalo)}"  # type: ignore[union-attr]
        alertas.append(
            Alerta(
                tipo=pior.tipo,
                sensor=sensor,
                severidade=pior.severidade,
                inicio=primeira.timestamp,
                fim=ultima.timestamp,
                leituras=len(grupo),
                valor_extremo=extremo.valor,
                unidade=unidade,
                limite=pior.limite,
                direcao=pior.direcao,
                leitura_suspeita=any(
                    FlagQualidade.FORA_FAIXA_PLAUSIVEL in medicoes[o.indice].flags for o in grupo
                ),
                detalhe=extremo.detalhe,
                mensagem=_mensagem(sensor, primeira.tipo, pior, extremo.valor, unidade, len(grupo)),
            )
        )
    return alertas


def _travamentos(
    sensor: str, medicoes: list[Medicao], em_lote: list[bool], minimo: int
) -> list[Alerta]:
    alertas = []
    for inicio, fim in regras.sequencias_iguais([m.valor for m in medicoes], minimo):
        if not any(em_lote[inicio : fim + 1]):
            continue
        m = medicoes[inicio]
        n = fim - inicio + 1
        alertas.append(
            Alerta(
                tipo=TipoAlerta.SENSOR_TRAVADO,
                sensor=sensor,
                severidade=Severidade.AVISO,
                inicio=m.timestamp,
                fim=medicoes[fim].timestamp,
                leituras=n,
                valor_extremo=m.valor,
                unidade=m.unidade,
                mensagem=f"{sensor}: {n} leituras seguidas com o mesmo valor ({m.valor:g} {m.unidade}); verificar o instrumento",
            )
        )
    return alertas


def _rotulo_intervalo(intervalo: timedelta) -> str:
    segundos = intervalo.total_seconds()
    for rotulo, base in (("dia", 86400), ("h", 3600), ("min", 60)):
        if segundos == base:
            return rotulo
    return f"{segundos:g}s"


def _mensagem(
    sensor: str, tipo: TipoMedicao, oc: _Ocorrencia, valor: float, unidade: str, leituras: int
) -> str:
    nivel = oc.severidade.name.lower()
    sufixo = f" em {leituras} leituras" if leituras > 1 else ""
    if oc.tipo is TipoAlerta.LIMITE:
        return (
            f"{sensor}: {tipo.value} {valor:g} {unidade} {oc.direcao} do limite de {nivel} "
            f"({oc.limite:g} {unidade}){sufixo}"
        )
    if oc.tipo is TipoAlerta.TAXA_VARIACAO:
        return f"{sensor}: {oc.direcao} de {abs(valor):g} {unidade}, acima do limite de {nivel} ({oc.limite:g} {unidade})"
    if oc.tipo is TipoAlerta.FORA_FAIXA_PLAUSIVEL:
        return f"{sensor}: leitura {valor:g} {unidade} fora da faixa do instrumento{sufixo}; verificar sensor"
    return f"{sensor}: leitura {valor:g} {unidade} destoa do comportamento recente (|z| > {oc.limite:g})"
