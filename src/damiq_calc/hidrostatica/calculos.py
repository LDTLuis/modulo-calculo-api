"""Cálculos de hidrostática e piezometria.

Fonte: Apostila BCST (AP) – Nota 10 (empuxo, barragens de gravidade) e Nota 11
(interpretação de redes de fluxo, subpressão). Resultados por metro de comprimento da
barragem, salvo quando o comprimento é informado.
"""

from __future__ import annotations

import math

from damiq_calc.core.calculo import GAMA_W, Entrada, Memoria, calculo, erro_campo, fmt
from damiq_calc.core.resultado import Resultado

FONTE_REDE_FLUXO = "AP, Nota 11 – Interpretação de redes de fluxo"
FONTE_EMPUXO = "AP, Nota 10 – Empuxo em barramentos"

COMPRIMENTO = Entrada(
    "comprimento",
    "Comprimento da barragem (opcional; sem ele, resultados por metro)",
    "m",
    minimo=0,
    minimo_inclusivo=False,
    opcional=True,
)


def _r(calculo_id: str, descricao: str, valor: float, unidade: str, fonte: str, mem: Memoria) -> Resultado:
    return Resultado(
        calculo=calculo_id,
        descricao=descricao,
        valor=valor,
        unidade=unidade,
        premissas=tuple(mem.premissas),
        fonte=fonte,
    )


@calculo(
    "hidrostatica.pressao",
    "Pressão hidrostática em profundidade",
    FONTE_EMPUXO,
    (
        Entrada("profundidade", "Profundidade abaixo do nível d'água (h)", "m", minimo=0),
        GAMA_W,
    ),
)
def pressao(e, mem: Memoria) -> list[Resultado]:
    h, gw = e["profundidade"], e["gama_w"]
    p = mem.passo("Pressão hidrostática", "p = γw · h", f"p = {fmt(gw)} · {fmt(h)}", gw * h, "kPa")
    return [_r("hidrostatica.pressao", "Pressão hidrostática", p, "kPa", FONTE_EMPUXO, mem)]


@calculo(
    "hidrostatica.piezometro",
    "Carga e cota piezométrica a partir da leitura do piezômetro",
    FONTE_REDE_FLUXO,
    (
        Entrada("pressao", "Pressão lida no piezômetro (u)", "kPa"),
        Entrada("cota_instalacao", "Cota de instalação do sensor", "m"),
        GAMA_W,
    ),
)
def piezometro(e, mem: Memoria) -> list[Resultado]:
    u, cota, gw = e["pressao"], e["cota_instalacao"], e["gama_w"]
    hp = mem.passo("Carga piezométrica", "hp = u / γw", f"hp = {fmt(u)} / {fmt(gw)}", u / gw, "m")
    cp = mem.passo(
        "Cota piezométrica (nível d'água no piezômetro)",
        "cota_p = cota_instalação + hp",
        f"cota_p = {fmt(cota)} + {fmt(hp)}",
        cota + hp,
        "m",
    )
    if u < 0:
        mem.premissa("Pressão negativa (sucção): carga piezométrica abaixo da cota do sensor")
    return [
        _r("hidrostatica.piezometro.carga", "Carga piezométrica", hp, "m", FONTE_REDE_FLUXO, mem),
        _r("hidrostatica.piezometro.cota", "Cota piezométrica", cp, "m", FONTE_REDE_FLUXO, mem),
    ]


@calculo(
    "hidrostatica.carga_rede_fluxo",
    "Cargas e pressão em um ponto da fundação (rede de fluxo)",
    FONTE_REDE_FLUXO,
    (
        Entrada("cota_na_montante", "Carga total a montante: cota do NA do reservatório", "m"),
        Entrada("perda_carga_total", "Perda de carga total (h): NA montante − NA jusante", "m", minimo=0, minimo_inclusivo=False),
        Entrada("n_d", "Número de quedas de potencial da rede (N_D)", minimo=1, inteiro=True),
        Entrada("quedas_percorridas", "Quedas de potencial percorridas até o ponto (n)", minimo=0, inteiro=True),
        Entrada("cota_ponto", "Cota do ponto (carga altimétrica)", "m"),
        GAMA_W,
    ),
)
def carga_rede_fluxo(e, mem: Memoria) -> list[Resultado]:
    na, h, nd, n, cota, gw = (
        e["cota_na_montante"], e["perda_carga_total"], e["n_d"], e["quedas_percorridas"], e["cota_ponto"], e["gama_w"],
    )
    if n > nd:
        raise erro_campo("quedas_percorridas", f"não pode exceder N_D ({fmt(nd)})", "FORA_DO_INTERVALO")
    dh = mem.passo("Perda de carga por queda de potencial", "Δh = h / N_D", f"Δh = {fmt(h)} / {fmt(nd)}", h / nd, "m")
    ht = mem.passo("Carga total no ponto", "Ht = NA_montante − n · Δh", f"Ht = {fmt(na)} − {fmt(n)} · {fmt(dh)}", na - n * dh, "m")
    ha = mem.passo("Carga altimétrica", "Ha = cota do ponto", "Ha = cota do ponto", cota, "m")
    hp = mem.passo("Carga piezométrica", "Hp = Ht − Ha", f"Hp = {fmt(ht)} − {fmt(ha)}", ht - ha, "m")
    u = mem.passo("Pressão da água no ponto", "u = γw · Hp", f"u = {fmt(gw)} · {fmt(hp)}", gw * hp, "kPa")
    return [
        _r("hidrostatica.carga_rede_fluxo.delta_h", "Perda de carga por queda", dh, "m", FONTE_REDE_FLUXO, mem),
        _r("hidrostatica.carga_rede_fluxo.carga_total", "Carga total", ht, "m", FONTE_REDE_FLUXO, mem),
        _r("hidrostatica.carga_rede_fluxo.carga_piezometrica", "Carga piezométrica", hp, "m", FONTE_REDE_FLUXO, mem),
        _r("hidrostatica.carga_rede_fluxo.pressao", "Pressão da água", u, "kPa", FONTE_REDE_FLUXO, mem),
    ]


@calculo(
    "hidrostatica.empuxo",
    "Empuxo hidrostático no paramento de montante",
    FONTE_EMPUXO,
    (
        Entrada("altura_agua", "Altura da lâmina d'água sobre a base (h)", "m", minimo=0, minimo_inclusivo=False),
        Entrada(
            "inclinacao_montante",
            "Inclinação do paramento de montante, H:V (0 = vertical; 3 = talude 3:1)",
            minimo=0,
            padrao=0.0,
        ),
        COMPRIMENTO,
        GAMA_W,
    ),
)
def empuxo(e, mem: Memoria) -> list[Resultado]:
    h, m, comp, gw = e["altura_agua"], e["inclinacao_montante"], e["comprimento"], e["gama_w"]
    eh = mem.passo(
        "Empuxo horizontal (área do diagrama triangular de pressões)",
        "Eh = γw · h² / 2",
        f"Eh = {fmt(gw)} · {fmt(h)}² / 2",
        gw * h**2 / 2,
        "kN/m",
    )
    yh = mem.passo("Ponto de aplicação de Eh, acima da base", "y = h / 3", f"y = {fmt(h)} / 3", h / 3, "m")
    fonte = FONTE_EMPUXO
    resultados = [
        _r("hidrostatica.empuxo.horizontal", "Empuxo horizontal", eh, "kN/m", fonte, mem),
        _r("hidrostatica.empuxo.braco_horizontal", "Altura de aplicação do empuxo horizontal", yh, "m", fonte, mem),
    ]
    if m > 0:
        ev = mem.passo(
            "Componente vertical: peso da água sobre o paramento inclinado",
            "Ev = γw · m · h² / 2",
            f"Ev = {fmt(gw)} · {fmt(m)} · {fmt(h)}² / 2",
            gw * m * h**2 / 2,
            "kN/m",
        )
        xv = mem.passo(
            "Ponto de aplicação de Ev, a partir do pé de montante",
            "x = m · h / 3",
            f"x = {fmt(m)} · {fmt(h)} / 3",
            m * h / 3,
            "m",
        )
        er = mem.passo("Empuxo resultante", "E = √(Eh² + Ev²)", f"E = √({fmt(eh)}² + {fmt(ev)}²)", math.hypot(eh, ev), "kN/m")
        resultados += [
            _r("hidrostatica.empuxo.vertical", "Empuxo vertical (peso da água)", ev, "kN/m", fonte, mem),
            _r("hidrostatica.empuxo.braco_vertical", "Distância de aplicação do empuxo vertical", xv, "m", fonte, mem),
            _r("hidrostatica.empuxo.resultante", "Empuxo resultante", er, "kN/m", fonte, mem),
        ]
    else:
        er = eh
    if comp is not None:
        total = mem.passo("Empuxo resultante total", "E_total = E · L", f"E_total = {fmt(er)} · {fmt(comp)}", er * comp, "kN")
        resultados.append(_r("hidrostatica.empuxo.total", "Empuxo resultante total", total, "kN", fonte, mem))
    return resultados


@calculo(
    "hidrostatica.subpressao",
    "Subpressão na base da barragem (diagrama trapezoidal)",
    FONTE_REDE_FLUXO,
    (
        Entrada("largura_base", "Largura da base da barragem (B)", "m", minimo=0, minimo_inclusivo=False),
        Entrada("pressao_montante", "Pressão da água sob o pé de montante (u1)", "kPa", minimo=0),
        Entrada("pressao_jusante", "Pressão da água sob o pé de jusante (u2)", "kPa", minimo=0),
        COMPRIMENTO,
    ),
)
def subpressao(e, mem: Memoria) -> list[Resultado]:
    b, u1, u2, comp = e["largura_base"], e["pressao_montante"], e["pressao_jusante"], e["comprimento"]
    fonte = FONTE_REDE_FLUXO
    u = mem.passo(
        "Subpressão por metro (área do diagrama trapezoidal)",
        "U = B · (u1 + u2) / 2",
        f"U = {fmt(b)} · ({fmt(u1)} + {fmt(u2)}) / 2",
        b * (u1 + u2) / 2,
        "kN/m",
    )
    resultados = [_r("hidrostatica.subpressao.por_metro", "Subpressão por metro", u, "kN/m", fonte, mem)]
    if u1 + u2 > 0:
        x = mem.passo(
            "Ponto de aplicação, a partir do pé de montante (centroide do trapézio)",
            "x = B · (u1 + 2·u2) / [3 · (u1 + u2)]",
            f"x = {fmt(b)} · ({fmt(u1)} + 2·{fmt(u2)}) / [3 · ({fmt(u1)} + {fmt(u2)})]",
            b * (u1 + 2 * u2) / (3 * (u1 + u2)),
            "m",
        )
        resultados.append(_r("hidrostatica.subpressao.braco", "Ponto de aplicação da subpressão", x, "m", fonte, mem))
    if comp is not None:
        total = mem.passo("Subpressão total", "U_total = U · L", f"U_total = {fmt(u)} · {fmt(comp)}", u * comp, "kN")
        resultados.append(_r("hidrostatica.subpressao.total", "Subpressão total", total, "kN", fonte, mem))
    return resultados
