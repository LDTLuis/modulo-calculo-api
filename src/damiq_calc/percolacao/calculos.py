"""Cálculos de percolação e erosão interna.

Fonte: Apostila BCST (AP) – Nota 11 (Lei de Darcy, fluxo bidimensional, redes de fluxo,
areia movediça, piping e filtros de proteção). Vazões por metro de comprimento da
barragem, salvo quando o comprimento é informado.
"""

from __future__ import annotations

from damiq_calc.core.calculo import (
    GAMA_W,
    Entrada,
    Limite,
    Memoria,
    calculo,
    classificar_fs,
    erro_campo,
    fmt,
    resultado,
)
from damiq_calc.core.resultado import Severidade

FONTE = "AP, Nota 11 – Fluxo de rede e gradiente hidráulico"
FONTE_PIPING = "AP, Nota 11 – Redes de fluxo, Exercício 2 (areia movediça)"
FONTE_FILTRO = "AP, Nota 11 – Critérios de filtro de Terzaghi"

FS_MIN_PIPING = Limite("fs_min_piping", "FS mínimo contra areia movediça/piping (i_crit / i_saída)", 1.5)
FATOR_TERZAGHI = Limite("fator_filtro_terzaghi", "Fator dos critérios de filtro de Terzaghi", 5.0)

K = Entrada("k", "Coeficiente de permeabilidade do solo (k)", "m/s", minimo=0, minimo_inclusivo=False)
PERDA_CARGA = Entrada(
    "perda_carga_total",
    "Perda de carga total (h): NA montante − NA jusante",
    "m",
    minimo=0,
    minimo_inclusivo=False,
)
N_D = Entrada("n_d", "Número de quedas de potencial da rede (N_D)", minimo=1, inteiro=True)
COMPRIMENTO = Entrada(
    "comprimento",
    "Comprimento da barragem (opcional; sem ele, vazão por metro)",
    "m",
    minimo=0,
    minimo_inclusivo=False,
    opcional=True,
)


@calculo(
    "percolacao.darcy",
    "Lei de Darcy: gradiente, velocidade e vazão",
    FONTE,
    (
        K,
        Entrada("perda_carga", "Perda de carga ao longo do percurso (Δh)", "m", minimo=0),
        Entrada("comprimento_percurso", "Comprimento do percurso de percolação (L)", "m", minimo=0, minimo_inclusivo=False),
        Entrada("area", "Área da seção de escoamento (A), opcional", "m2", minimo=0, minimo_inclusivo=False, opcional=True),
    ),
)
def darcy(e, mem: Memoria):
    k, dh, comp, area = e["k"], e["perda_carga"], e["comprimento_percurso"], e["area"]
    i = mem.passo("Gradiente hidráulico", "i = Δh / L", f"i = {fmt(dh)} / {fmt(comp)}", dh / comp, "-")
    v = mem.passo("Velocidade de descarga", "v = k · i", f"v = {fmt(k)} · {fmt(i)}", k * i, "m/s")
    resultados = [
        resultado(mem, "percolacao.darcy.gradiente", "Gradiente hidráulico", i, "-", FONTE),
        resultado(mem, "percolacao.darcy.velocidade", "Velocidade de descarga", v, "m/s", FONTE),
    ]
    if area is not None:
        q = mem.passo("Vazão", "Q = k · i · A", f"Q = {fmt(k)} · {fmt(i)} · {fmt(area)}", k * i * area, "m3/s")
        resultados.append(resultado(mem, "percolacao.darcy.vazao", "Vazão", q, "m3/s", FONTE))
    return resultados


@calculo(
    "percolacao.vazao_rede_fluxo",
    "Vazão de percolação pela rede de fluxo",
    FONTE,
    (
        K,
        PERDA_CARGA,
        Entrada("n_f", "Número de canais de fluxo da rede (N_F)", minimo=1, inteiro=True),
        N_D,
        COMPRIMENTO,
    ),
)
def vazao_rede_fluxo(e, mem: Memoria):
    k, h, nf, nd, comp = e["k"], e["perda_carga_total"], e["n_f"], e["n_d"], e["comprimento"]
    q = mem.passo(
        "Vazão por metro de barragem",
        "Q = k · h · N_F / N_D",
        f"Q = {fmt(k)} · {fmt(h)} · {fmt(nf)} / {fmt(nd)}",
        k * h * nf / nd,
        "m3/s/m",
    )
    resultados = [resultado(mem, "percolacao.vazao_rede_fluxo.por_metro", "Vazão por metro", q, "m3/s/m", FONTE)]
    if comp is not None:
        total = mem.passo("Vazão total", "Q_total = Q · L", f"Q_total = {fmt(q)} · {fmt(comp)}", q * comp, "m3/s")
        resultados.append(resultado(mem, "percolacao.vazao_rede_fluxo.total", "Vazão total", total, "m3/s", FONTE))
    return resultados


@calculo(
    "percolacao.piping",
    "Gradiente de saída e FS contra areia movediça (piping)",
    FONTE_PIPING,
    (
        PERDA_CARGA,
        N_D,
        Entrada(
            "comprimento_celula",
            "Distância entre as duas últimas equipotenciais na face de saída (l)",
            "m",
            minimo=0,
            minimo_inclusivo=False,
        ),
        Entrada("gama_sat", "Peso específico saturado do solo da fundação (γsat)", "kN/m3", minimo=0, minimo_inclusivo=False),
        GAMA_W,
    ),
    limites=(FS_MIN_PIPING,),
)
def piping(e, mem: Memoria):
    h, nd, l, gsat, gw = e["perda_carga_total"], e["n_d"], e["comprimento_celula"], e["gama_sat"], e["gama_w"]
    if gsat <= gw:
        raise erro_campo("gama_sat", f"deve ser maior que γw ({fmt(gw)} kN/m3)", "FORA_DO_INTERVALO")
    fs_min = mem.limite("fs_min_piping")

    dh = mem.passo("Perda de carga por queda de potencial", "Δh = h / N_D", f"Δh = {fmt(h)} / {fmt(nd)}", h / nd, "m")
    i = mem.passo("Gradiente de saída (fluxo ascendente a jusante)", "i = Δh / l", f"i = {fmt(dh)} / {fmt(l)}", dh / l, "-")
    icrit = mem.passo(
        "Gradiente crítico (tensão efetiva nula)",
        "i_crit = (γsat − γw) / γw",
        f"i_crit = ({fmt(gsat)} − {fmt(gw)}) / {fmt(gw)}",
        (gsat - gw) / gw,
        "-",
    )
    fs = mem.passo("Fator de segurança contra areia movediça", "FS = i_crit / i", f"FS = {fmt(icrit)} / {fmt(i)}", icrit / i, "-")
    severidade = classificar_fs(fs, fs_min)
    if severidade is Severidade.OK:
        mem.conclusao(f"FS = {fmt(round(fs, 2))} ≥ {fmt(fs_min)}: atende ao critério contra areia movediça.")
    else:
        mem.conclusao(
            f"FS = {fmt(round(fs, 2))} < {fmt(fs_min)}: não atende. Risco de erosão regressiva a jusante; "
            "avaliar aumentar o caminho de percolação, pranchada ou filtro/berma no pé de jusante (AP)."
        )
    return [
        resultado(mem, "percolacao.piping.delta_h", "Perda de carga por queda", dh, "m", FONTE_PIPING),
        resultado(mem, "percolacao.piping.gradiente_saida", "Gradiente de saída", i, "-", FONTE_PIPING),
        resultado(mem, "percolacao.piping.gradiente_critico", "Gradiente crítico", icrit, "-", FONTE_PIPING),
        resultado(mem, "percolacao.piping.fs", "FS contra areia movediça", fs, "-", FONTE_PIPING, severidade, fs_min),
    ]


@calculo(
    "percolacao.filtro_terzaghi",
    "Verificação de filtro de proteção (critérios de Terzaghi)",
    FONTE_FILTRO,
    (
        Entrada("d15_filtro", "Diâmetro D15 do material do filtro", "mm", minimo=0, minimo_inclusivo=False),
        Entrada("d15_solo", "Diâmetro D15 do solo protegido", "mm", minimo=0, minimo_inclusivo=False),
        Entrada("d85_solo", "Diâmetro D85 do solo protegido", "mm", minimo=0, minimo_inclusivo=False),
    ),
    limites=(FATOR_TERZAGHI,),
)
def filtro_terzaghi(e, mem: Memoria):
    d15f, d15s, d85s = e["d15_filtro"], e["d15_solo"], e["d85_solo"]
    if d15s > d85s:
        raise erro_campo("d15_solo", "D15 do solo não pode ser maior que D85", "FORA_DO_INTERVALO")
    fator = mem.limite("fator_filtro_terzaghi")

    perm = mem.passo(
        "Critério de permeabilidade (filtro mais permeável que o solo)",
        f"D15_filtro / D15_solo > {fmt(fator)}",
        f"{fmt(d15f)} / {fmt(d15s)}",
        d15f / d15s,
        "-",
    )
    ret = mem.passo(
        "Critério de retenção (finos do solo não passam pelo filtro)",
        f"D15_filtro / D85_solo < {fmt(fator)}",
        f"{fmt(d15f)} / {fmt(d85s)}",
        d15f / d85s,
        "-",
    )
    atende_perm, atende_ret = perm > fator, ret < fator
    mem.conclusao(
        f"Permeabilidade: {fmt(round(perm, 2))} {'>' if atende_perm else '≤'} {fmt(fator)} — "
        f"{'atende' if atende_perm else 'não atende (filtro pouco permeável)'}."
    )
    mem.conclusao(
        f"Retenção: {fmt(round(ret, 2))} {'<' if atende_ret else '≥'} {fmt(fator)} — "
        f"{'atende' if atende_ret else 'não atende (filtro grosso demais, permite a passagem de finos)'}."
    )

    def sev(atende: bool) -> Severidade:
        return Severidade.OK if atende else Severidade.ALERTA

    return [
        resultado(mem, "percolacao.filtro_terzaghi.permeabilidade", "Razão D15f/D15s (deve ser > fator)", perm, "-", FONTE_FILTRO, sev(atende_perm), fator),
        resultado(mem, "percolacao.filtro_terzaghi.retencao", "Razão D15f/D85s (deve ser < fator)", ret, "-", FONTE_FILTRO, sev(atende_ret), fator),
    ]
