"""Cálculos de hidrologia.

Fonte: Apostila BCST (AP) – Notas 01 (outorga, índice de demanda), 02/03 (volume da represa,
vazão de base, extravasor), 04 (vazões, Método Racional) e 06 (período de retorno).
"""

from __future__ import annotations

from damiq_calc.core.calculo import (
    Entrada,
    EntradaTabela,
    Memoria,
    calculo,
    erro_campo,
    fmt,
    resultado,
)
from damiq_calc.core.resultado import Severidade

FONTE_VOLUME = "AP, Nota 03 – Volume de água armazenado"
FONTE_VAZAO = "AP, Nota 02 – Vazão de base"
FONTE_RACIONAL = "AP, Nota 04 – Método Racional"
FONTE_TR = "AP, Nota 06 – Recorrência / período de retorno"
FONTE_DEMANDA = "AP, Nota 01 – Outorga: análise de disponibilidade hídrica"
FONTE_EXTRAVASOR = "AP, Nota 02 – Aspectos construtivos: extravasor"

AREA_MAX_RACIONAL_HA = 200.0


# --- volume do reservatório ---------------------------------------------------------------


@calculo(
    "hidrologia.curva_cota_volume",
    "Curva cota–área–volume do reservatório (curvas de nível)",
    FONTE_VOLUME,
    (
        EntradaTabela(
            "pontos",
            "Curvas de nível: cota e área inundada até cada curva (a mais baixa, geralmente com área 0)",
            (
                Entrada("cota", "Cota da curva de nível", "m"),
                Entrada("area", "Área definida pela curva", "m2", minimo=0),
            ),
            min_linhas=2,
        ),
        Entrada("cota_consulta", "Cota para consultar volume e área (opcional; ex.: NA medido)", "m", opcional=True),
    ),
)
def curva_cota_volume(e, mem: Memoria):
    pontos = sorted(e["pontos"], key=lambda p: p["cota"])
    for anterior, atual in zip(pontos, pontos[1:]):
        if atual["cota"] == anterior["cota"]:
            raise erro_campo("pontos", f"cota {fmt(atual['cota'])} m repetida")

    acumulado = 0.0
    curva = [(pontos[0]["cota"], pontos[0]["area"], 0.0)]
    linhas = [[pontos[0]["cota"], pontos[0]["area"], 0.0, 0.0, 0.0]]
    for anterior, atual in zip(pontos, pontos[1:]):
        area_media = (anterior["area"] + atual["area"]) / 2
        dh = atual["cota"] - anterior["cota"]
        v = area_media * dh
        acumulado += v
        curva.append((atual["cota"], atual["area"], acumulado))
        linhas.append([atual["cota"], atual["area"], area_media, dh, v])
    mem.tabela(
        "Volume entre curvas de nível sucessivas",
        [("cota", "m"), ("área", "m2"), ("área média", "m2"), ("Δh", "m"), ("Vn = (Sn + Sn−1)/2 · Δh", "m3")],
        linhas,
    )
    total = mem.passo(
        "Volume total até a curva mais alta",
        "V = Σ (Sn + Sn−1)/2 · Δh",
        " + ".join(fmt(linha[4]) for linha in linhas[1:]),
        acumulado,
        "m3",
    )
    fonte = FONTE_VOLUME
    resultados = [
        resultado(mem, "hidrologia.curva_cota_volume.volume_total", f"Volume até a cota {fmt(curva[-1][0])} m", total, "m3", fonte),
    ]

    z = e["cota_consulta"]
    if z is not None:
        if not curva[0][0] <= z <= curva[-1][0]:
            raise erro_campo(
                "cota_consulta",
                f"fora da curva informada ({fmt(curva[0][0])} a {fmt(curva[-1][0])} m)",
                "FORA_DO_INTERVALO",
            )
        for (z0, s0, v0), (z1, s1, v1) in zip(curva, curva[1:]):
            if z0 <= z <= z1:
                break
        area_z = mem.passo(
            "Área do espelho d'água na cota consultada (interpolação linear)",
            "S(z) = S0 + (S1 − S0)·(z − z0)/(z1 − z0)",
            f"S = {fmt(s0)} + ({fmt(s1)} − {fmt(s0)})·({fmt(z)} − {fmt(z0)})/({fmt(z1)} − {fmt(z0)})",
            s0 + (s1 - s0) * (z - z0) / (z1 - z0),
            "m2",
        )
        vol_z = mem.passo(
            "Volume armazenado na cota consultada",
            "V(z) = V0 + (S0 + S(z))/2 · (z − z0)",
            f"V = {fmt(v0)} + ({fmt(s0)} + {fmt(area_z)})/2 · ({fmt(z)} − {fmt(z0)})",
            v0 + (s0 + area_z) / 2 * (z - z0),
            "m3",
        )
        resultados += [
            resultado(mem, "hidrologia.curva_cota_volume.area_consulta", f"Área do espelho na cota {fmt(z)} m", area_z, "m2", fonte),
            resultado(mem, "hidrologia.curva_cota_volume.volume_consulta", f"Volume na cota {fmt(z)} m", vol_z, "m3", fonte),
        ]
    return resultados


@calculo(
    "hidrologia.volume_secoes",
    "Volume por seções transversais",
    FONTE_VOLUME,
    (
        EntradaTabela(
            "secoes",
            "Seções: área molhada e distância de influência de cada uma",
            (
                Entrada("area", "Área da seção", "m2", minimo=0),
                Entrada("distancia", "Distância de influência da seção (d)", "m", minimo=0),
            ),
        ),
    ),
)
def volume_secoes(e, mem: Memoria):
    secoes = e["secoes"]
    mem.tabela(
        "Volume por seção",
        [("área", "m2"), ("d", "m"), ("V = A · d", "m3")],
        [[s["area"], s["distancia"], s["area"] * s["distancia"]] for s in secoes],
    )
    v = mem.passo("Volume total", "V = Σ Aᵢ · dᵢ", " + ".join(f"{fmt(s['area'])}·{fmt(s['distancia'])}" for s in secoes), sum(s["area"] * s["distancia"] for s in secoes), "m3")
    return [resultado(mem, "hidrologia.volume_secoes.volume", "Volume", v, "m3", FONTE_VOLUME)]


# --- vazões -------------------------------------------------------------------------------


@calculo(
    "hidrologia.vazao_medida",
    "Vazão de base medida (volume / tempo médio)",
    FONTE_VAZAO,
    (
        Entrada("volume", "Volume do recipiente (tambor)", "m3", minimo=0, minimo_inclusivo=False),
        EntradaTabela(
            "tempos",
            "Tempos de enchimento de cada repetição (a apostila sugere três)",
            (Entrada("tempo", "Tempo de enchimento", "s", minimo=0, minimo_inclusivo=False),),
        ),
    ),
)
def vazao_medida(e, mem: Memoria):
    volume, tempos = e["volume"], [t["tempo"] for t in e["tempos"]]
    if len(tempos) < 3:
        mem.premissa(f"Apenas {len(tempos)} repetição(ões); a apostila recomenda três")
    t_medio = mem.passo("Tempo médio", "t = Σ tᵢ / n", f"t = ({' + '.join(fmt(t) for t in tempos)}) / {len(tempos)}", sum(tempos) / len(tempos), "s")
    q = mem.passo("Vazão", "Q = Volume / t", f"Q = {fmt(volume)} / {fmt(t_medio)}", volume / t_medio, "m3/s")
    return [
        resultado(mem, "hidrologia.vazao_medida.tempo_medio", "Tempo médio", t_medio, "s", FONTE_VAZAO),
        resultado(mem, "hidrologia.vazao_medida.vazao", "Vazão de base", q, "m3/s", FONTE_VAZAO),
    ]


@calculo(
    "hidrologia.metodo_racional",
    "Vazão de cheia pelo Método Racional",
    FONTE_RACIONAL,
    (
        Entrada("coeficiente_escoamento", "Coeficiente de escoamento superficial (C)", minimo=0, minimo_inclusivo=False, maximo=1),
        Entrada("intensidade", "Intensidade da chuva de projeto (i)", "mm/h", minimo=0, minimo_inclusivo=False),
        Entrada("area", "Área da bacia de contribuição (A)", "ha", minimo=0, minimo_inclusivo=False),
    ),
)
def metodo_racional(e, mem: Memoria):
    c, i, a = e["coeficiente_escoamento"], e["intensidade"], e["area"]
    q = mem.passo("Vazão de pico", "Q = C · i · A / 360   (i em mm/h, A em ha)", f"Q = {fmt(c)} · {fmt(i)} · {fmt(a)} / 360", c * i * a / 360, "m3/s")
    severidade = Severidade.OK
    if a > AREA_MAX_RACIONAL_HA:
        severidade = Severidade.AVISO
        mem.premissa(f"A = {fmt(a)} ha > {fmt(AREA_MAX_RACIONAL_HA)} ha: fora do domínio de validade do Método Racional (AP)")
        mem.conclusao("Bacia maior que 200 ha: usar método de hidrograma unitário ou estudo hidrológico específico.")
    return [resultado(mem, "hidrologia.metodo_racional.vazao", "Vazão de pico", q, "m3/s", FONTE_RACIONAL, severidade, AREA_MAX_RACIONAL_HA if severidade else None)]


@calculo(
    "hidrologia.periodo_retorno",
    "Período de retorno a partir do risco admitido e da vida útil",
    FONTE_TR,
    (
        Entrada("risco", "Risco de falha admitido na vida útil (R); aceita %", minimo=0, minimo_inclusivo=False, maximo=1, maximo_inclusivo=False),
        Entrada("vida_util", "Vida útil da obra (n), em anos", minimo=1),
    ),
)
def periodo_retorno(e, mem: Memoria):
    r, n = e["risco"], e["vida_util"]
    tr = mem.passo(
        "Período de retorno",
        "Tr = 1 / [1 − (1 − R)^(1/n)]",
        f"Tr = 1 / [1 − (1 − {fmt(r)})^(1/{fmt(n)})]",
        1 / (1 - (1 - r) ** (1 / n)),
        "anos",
    )
    return [resultado(mem, "hidrologia.periodo_retorno.tr", "Período de retorno", tr, "anos", FONTE_TR)]


# --- disponibilidade hídrica e extravasor -------------------------------------------------

CLASSES_DEMANDA = (
    # (limite superior, inclusivo?, rótulo, severidade) – AP: Normal < 50%; Alerta 50–80%;
    # Moderadamente crítico 80–100%; Altamente crítico > 100%
    (50.0, False, "Normal", Severidade.OK),
    (80.0, False, "Alerta", Severidade.AVISO),
    (100.0, True, "Moderadamente crítico", Severidade.ALERTA),
    (float("inf"), True, "Altamente crítico", Severidade.CRITICO),
)


def classificar_demanda(indice_pct: float) -> tuple[str, Severidade]:
    for limite, inclusivo, rotulo, sev in CLASSES_DEMANDA:
        if indice_pct < limite or (inclusivo and indice_pct == limite):
            return rotulo, sev
    raise AssertionError("inalcançável")


@calculo(
    "hidrologia.indice_demanda",
    "Índice de demanda (comprometimento da vazão de referência)",
    FONTE_DEMANDA,
    (
        Entrada("vazao_especifica", "Vazão específica de referência da região (Qesp)", "m3/s/km2", minimo=0, minimo_inclusivo=False),
        Entrada("area_drenagem", "Área de drenagem até o barramento (AD)", "km2", minimo=0, minimo_inclusivo=False),
        Entrada("vazao_consumo", "Vazão de consumo / captação (Qconsumo)", "m3/s", minimo=0),
    ),
)
def indice_demanda(e, mem: Memoria):
    qesp, ad, qc = e["vazao_especifica"], e["area_drenagem"], e["vazao_consumo"]
    qref = mem.passo("Vazão de referência", "Qref = Qesp · AD", f"Qref = {fmt(qesp)} · {fmt(ad)}", qesp * ad, "m3/s")
    indice = mem.passo("Índice de demanda", "ID = Qconsumo / Qref · 100", f"ID = {fmt(qc)} / {fmt(qref)} · 100", qc / qref * 100, "%")
    rotulo, sev = classificar_demanda(indice)
    mem.conclusao(f"ID = {fmt(round(indice, 1))}%: {rotulo} (Normal < 50%; Alerta 50–80%; Moderadamente crítico 80–100%; Altamente crítico > 100%).")
    return [
        resultado(mem, "hidrologia.indice_demanda.vazao_referencia", "Vazão de referência", qref, "m3/s", FONTE_DEMANDA),
        resultado(mem, "hidrologia.indice_demanda.indice", "Índice de demanda", indice, "%", FONTE_DEMANDA, sev, rotulo=rotulo),
    ]


@calculo(
    "hidrologia.extravasor",
    "Verificação da capacidade do extravasor",
    FONTE_EXTRAVASOR,
    (
        Entrada("vazao_projeto", "Vazão de projeto (ex.: Método Racional com a chuva de Tr adotado)", "m3/s", minimo=0, minimo_inclusivo=False),
        Entrada("capacidade", "Capacidade de descarga do extravasor", "m3/s", minimo=0),
    ),
)
def extravasor(e, mem: Memoria):
    qp, cap = e["vazao_projeto"], e["capacidade"]
    razao = mem.passo("Relação capacidade / vazão de projeto", "r = Q_capacidade / Q_projeto", f"r = {fmt(cap)} / {fmt(qp)}", cap / qp, "-")
    folga = mem.passo("Folga de descarga", "ΔQ = Q_capacidade − Q_projeto", f"ΔQ = {fmt(cap)} − {fmt(qp)}", cap - qp, "m3/s")
    if razao >= 1:
        sev = Severidade.OK
        mem.conclusao(f"Extravasor comporta a vazão de projeto (r = {fmt(round(razao, 2))}).")
    else:
        sev = Severidade.CRITICO
        mem.conclusao(f"Extravasor subdimensionado (r = {fmt(round(razao, 2))}): risco de galgamento do maciço.")
    return [
        resultado(mem, "hidrologia.extravasor.razao", "Capacidade / vazão de projeto", razao, "-", FONTE_EXTRAVASOR, sev, 1.0),
        resultado(mem, "hidrologia.extravasor.folga", "Folga de descarga", folga, "m3/s", FONTE_EXTRAVASOR, sev),
    ]
