"""Cálculos de geometria do maciço de terra.

Fonte: Apostila BCST (AP) – Nota 02 (características do maciço: taludes 3:1 a montante e
2:1 a jusante, crista mínima de 2,5 m; volume de terra por trapézios; relação volume de
água : volume de terra ≥ 3:1; folga de 1,0 m acima do NA). As recomendações valem para
projetos novos; em barragens existentes, a apostila orienta verificar in loco — por isso o
não atendimento gera AVISO, não reprovação.

Inclinações de talude em H:V (3 = talude 3:1).
"""

from __future__ import annotations

from damiq_calc.core.calculo import (
    Entrada,
    EntradaTabela,
    Limite,
    Memoria,
    calculo,
    fmt,
    resultado,
)
from damiq_calc.core.resultado import Severidade

FONTE = "AP, Nota 02 – Características do maciço de terra"
FONTE_VOLUME = "AP, Nota 02 – Volume de terra empregado na construção"

CRISTA_MIN = Limite("largura_min_crista", "Largura mínima da crista (m)", 2.5)
TALUDE_MONTANTE_MIN = Limite("talude_min_montante", "Inclinação mínima recomendada do talude de montante (H:V)", 3.0)
TALUDE_JUSANTE_MIN = Limite("talude_min_jusante", "Inclinação mínima recomendada do talude de jusante (H:V)", 2.0)
BORDA_LIVRE_MIN = Limite("borda_livre_min", "Borda livre mínima acima do NA máximo (m)", 1.0)
RELACAO_AGUA_TERRA_MIN = Limite("relacao_min_agua_terra", "Relação mínima volume de água : volume de terra", 3.0)

CRISTA = Entrada("largura_crista", "Largura da crista (b)", "m", minimo=0, minimo_inclusivo=False)
TALUDE_MONTANTE = Entrada("talude_montante", "Inclinação do talude de montante, H:V (m₁)", minimo=0, minimo_inclusivo=False, padrao=3.0)
TALUDE_JUSANTE = Entrada("talude_jusante", "Inclinação do talude de jusante, H:V (m₂)", minimo=0, minimo_inclusivo=False, padrao=2.0)


def area_secao(h: float, b: float, m1: float, m2: float) -> float:
    """Seção trapezoidal: A = h·(2b + (m₁ + m₂)·h)/2."""
    return h * (2 * b + (m1 + m2) * h) / 2


@calculo(
    "geometria.secao_macico",
    "Seção transversal do maciço e conformidade de crista e taludes",
    FONTE,
    (
        Entrada("altura", "Altura do maciço (h)", "m", minimo=0, minimo_inclusivo=False),
        CRISTA,
        TALUDE_MONTANTE,
        TALUDE_JUSANTE,
    ),
    limites=(CRISTA_MIN, TALUDE_MONTANTE_MIN, TALUDE_JUSANTE_MIN),
)
def secao_macico(e, mem: Memoria):
    h, b, m1, m2 = e["altura"], e["largura_crista"], e["talude_montante"], e["talude_jusante"]
    base = mem.passo("Largura da base", "B = b + (m₁ + m₂)·h", f"B = {fmt(b)} + ({fmt(m1)} + {fmt(m2)})·{fmt(h)}", b + (m1 + m2) * h, "m")
    area = mem.passo(
        "Área da seção transversal",
        "A = h·(2b + (m₁ + m₂)·h)/2",
        f"A = {fmt(h)}·(2·{fmt(b)} + ({fmt(m1)} + {fmt(m2)})·{fmt(h)})/2",
        area_secao(h, b, m1, m2),
        "m2",
    )

    def verificar(valor: float, nome_limite: str, rotulo: str, unidade: str) -> tuple[Severidade, float]:
        minimo = mem.limite(nome_limite)
        atende = valor >= minimo
        mem.conclusao(
            f"{rotulo}: {fmt(valor)}{unidade} {'≥' if atende else '<'} {fmt(minimo)}{unidade} — "
            + ("atende à recomendação." if atende else "abaixo do recomendado para projetos novos; verificar in loco em barragens existentes.")
        )
        return (Severidade.OK if atende else Severidade.AVISO), minimo

    sev_b, lim_b = verificar(b, "largura_min_crista", "Crista", " m")
    sev_m, lim_m = verificar(m1, "talude_min_montante", "Talude de montante (H:V)", "")
    sev_j, lim_j = verificar(m2, "talude_min_jusante", "Talude de jusante (H:V)", "")
    return [
        resultado(mem, "geometria.secao_macico.largura_base", "Largura da base", base, "m", FONTE),
        resultado(mem, "geometria.secao_macico.area", "Área da seção", area, "m2", FONTE),
        resultado(mem, "geometria.secao_macico.crista", "Largura da crista", b, "m", FONTE, sev_b, lim_b),
        resultado(mem, "geometria.secao_macico.talude_montante", "Talude de montante (H:V)", m1, "-", FONTE, sev_m, lim_m),
        resultado(mem, "geometria.secao_macico.talude_jusante", "Talude de jusante (H:V)", m2, "-", FONTE, sev_j, lim_j),
    ]


@calculo(
    "geometria.volume_terra",
    "Volume de terra do maciço por trapézios",
    FONTE_VOLUME,
    (
        CRISTA,
        TALUDE_MONTANTE,
        TALUDE_JUSANTE,
        EntradaTabela(
            "trechos",
            "Trechos do eixo: altura do maciço e comprimento de cada trecho",
            (
                Entrada("altura", "Altura do maciço no trecho (h)", "m", minimo=0),
                Entrada("comprimento", "Comprimento do trecho ao longo do eixo (L)", "m", minimo=0, minimo_inclusivo=False),
            ),
        ),
        Entrada("volume_agua", "Volume de água acumulado (opcional, para a relação água : terra)", "m3", minimo=0, minimo_inclusivo=False, opcional=True),
    ),
    limites=(RELACAO_AGUA_TERRA_MIN,),
)
def volume_terra(e, mem: Memoria):
    b, m1, m2, trechos = e["largura_crista"], e["talude_montante"], e["talude_jusante"], e["trechos"]
    linhas = []
    for t in trechos:
        a = area_secao(t["altura"], b, m1, m2)
        linhas.append([t["altura"], t["comprimento"], a, a * t["comprimento"]])
    mem.tabela(
        "Volume por trapézio",
        [("h", "m"), ("L", "m"), ("A = h·(2b + (m₁+m₂)·h)/2", "m2"), ("V = A · L", "m3")],
        linhas,
    )
    total = mem.passo("Volume total de terra", "V = Σ Aᵢ · Lᵢ", " + ".join(fmt(linha[3]) for linha in linhas), sum(linha[3] for linha in linhas), "m3")
    resultados = [resultado(mem, "geometria.volume_terra.volume", "Volume de terra", total, "m3", FONTE_VOLUME)]

    va = e["volume_agua"]
    if va is not None:
        minimo = mem.limite("relacao_min_agua_terra")
        relacao = mem.passo("Relação água : terra", "r = V_água / V_terra", f"r = {fmt(va)} / {fmt(total)}", va / total, "-")
        atende = relacao >= minimo
        mem.conclusao(
            f"Relação água : terra = {fmt(round(relacao, 2))} {'≥' if atende else '<'} {fmt(minimo)}: "
            + ("empreendimento eficiente quanto ao volume de terra." if atende else "volume de terra desproporcional ao volume acumulado; rever o local ou a altura do barramento.")
        )
        resultados.append(
            resultado(mem, "geometria.volume_terra.relacao_agua_terra", "Relação água : terra", relacao, "-", FONTE_VOLUME, Severidade.OK if atende else Severidade.AVISO, minimo)
        )
    return resultados


@calculo(
    "geometria.borda_livre",
    "Borda livre (folga entre a crista e o NA máximo)",
    FONTE,
    (
        Entrada("cota_crista", "Cota da crista (coroamento)", "m"),
        Entrada("cota_na_maximo", "Cota do NA máximo (maximorum ou de projeto)", "m"),
    ),
    limites=(BORDA_LIVRE_MIN,),
)
def borda_livre(e, mem: Memoria):
    crista, na = e["cota_crista"], e["cota_na_maximo"]
    minimo = mem.limite("borda_livre_min")
    bl = mem.passo("Borda livre", "BL = cota_crista − NA_máx", f"BL = {fmt(crista)} − {fmt(na)}", crista - na, "m")
    if bl <= 0:
        sev = Severidade.CRITICO
        mem.conclusao("NA máximo atinge ou supera a crista: galgamento do maciço.")
    elif bl < minimo:
        sev = Severidade.ALERTA
        mem.conclusao(f"Borda livre {fmt(round(bl, 2))} m < {fmt(minimo)} m: folga insuficiente contra ondas e transbordamento.")
    else:
        sev = Severidade.OK
        mem.conclusao(f"Borda livre {fmt(round(bl, 2))} m ≥ {fmt(minimo)} m: atende.")
    return [resultado(mem, "geometria.borda_livre.borda_livre", "Borda livre", bl, "m", FONTE, sev, minimo)]
