"""Cálculos de estabilidade.

Fontes: Apostila BCST (AP) – Nota 09/10: estabilidade de taludes (NBR 11.682, FS ≥ 1,5;
método das fatias de Fellenius e Bishop) e barragens de gravidade (escorregamento
P·f ≥ E·n com f = 0,75 e n = 1,50; posição da resultante no terço médio da base).

Convenções:
- Taludes: a superfície de ruptura é informada já dividida em fatias (a busca do círculo
  crítico fica para uma próxima etapa). α é a inclinação da base da fatia, positiva quando
  a base sobe no sentido do movimento; u é a poropressão média na base.
- Gravidade: forças por metro de barragem; distâncias horizontais medidas a partir do pé de
  montante, alturas a partir da base.
"""

from __future__ import annotations

import math

from damiq_calc.core.calculo import (
    Entrada,
    EntradaTabela,
    Limite,
    Memoria,
    calculo,
    classificar_fs,
    erro_campo,
    fmt,
    resultado,
)
from damiq_calc.core.resultado import Severidade

FONTE_TALUDE = "AP, Nota 09 – Estabilidade de taludes (NBR 11.682; método das fatias)"
FONTE_GRAVIDADE = "AP, Nota 10 – Barragens de gravidade: condições de estabilidade"

FS_MIN_TALUDE = Limite("fs_min_talude", "FS mínimo de estabilidade de taludes (NBR 11.682)", 1.5)
FS_MIN_DESLIZAMENTO = Limite("fs_min_deslizamento", "Fator de segurança n contra escorregamento (P·f ≥ E·n)", 1.5)

_BISHOP_TOLERANCIA = 1e-6
_BISHOP_MAX_ITERACOES = 100
# m_α muito pequeno torna o Bishop instável (fatias com base muito íngreme contra o movimento).
_BISHOP_M_ALFA_MINIMO = 0.2

FATIAS = EntradaTabela(
    "fatias",
    "Fatias da superfície de ruptura",
    (
        Entrada("largura", "Largura da fatia (b)", "m", minimo=0, minimo_inclusivo=False),
        Entrada("peso", "Peso da fatia por metro (W)", "kN/m", minimo=0),
        Entrada("alfa", "Inclinação da base da fatia (α)", "grau", minimo=-90, minimo_inclusivo=False, maximo=90, maximo_inclusivo=False),
        Entrada("coesao", "Coesão efetiva do solo na base (c')", "kPa", minimo=0),
        Entrada("phi", "Ângulo de atrito efetivo na base (φ')", "grau", minimo=0, maximo=90, maximo_inclusivo=False),
        Entrada("poropressao", "Poropressão média na base (u)", "kPa", minimo=0, padrao=0.0),
    ),
    min_linhas=1,
)


def _fatias_em_radianos(fatias):
    return [
        {
            **f,
            "a": math.radians(f["alfa"]),
            "tphi": math.tan(math.radians(f["phi"])),
        }
        for f in fatias
    ]


def _momento_atuante(fatias, mem: Memoria) -> float:
    atuante = sum(f["peso"] * math.sin(f["a"]) for f in fatias)
    if atuante <= 0:
        raise erro_campo("fatias", "Σ W·sen α ≤ 0: a superfície não tem esforço instabilizante (verifique o sinal de α)")
    return mem.passo("Soma dos esforços instabilizantes", "ΣS = Σ W · sen α", "ΣS", atuante, "kN/m")


def _parecer_fs(mem: Memoria, fs: float, fs_min: float, severidade: Severidade, metodo: str) -> None:
    if severidade is Severidade.OK:
        mem.conclusao(f"{metodo}: FS = {fmt(round(fs, 2))} ≥ {fmt(fs_min)}: talude estável para a superfície analisada.")
    elif severidade is Severidade.ALERTA:
        mem.conclusao(f"{metodo}: FS = {fmt(round(fs, 2))} < {fmt(fs_min)}: não atende à NBR 11.682; avaliar abatimento do talude, bermas ou drenagem.")
    else:
        mem.conclusao(f"{metodo}: FS = {fmt(round(fs, 2))} < 1: ruptura esperada para a superfície analisada.")


@calculo(
    "estabilidade.talude_fellenius",
    "FS de talude pelo método das fatias de Fellenius",
    FONTE_TALUDE,
    (FATIAS,),
    limites=(FS_MIN_TALUDE,),
)
def talude_fellenius(e, mem: Memoria):
    fs_min = mem.limite("fs_min_talude")
    fatias = _fatias_em_radianos(e["fatias"])
    linhas = []
    resistente = 0.0
    for f in fatias:
        comp_base = f["largura"] / math.cos(f["a"])
        normal_efetiva = f["peso"] * math.cos(f["a"]) - f["poropressao"] * comp_base
        # Fellenius não admite normal efetiva negativa: sem atrito nessa fatia.
        r = f["coesao"] * comp_base + max(normal_efetiva, 0.0) * f["tphi"]
        resistente += r
        linhas.append([f["largura"], f["peso"], f["alfa"], comp_base, normal_efetiva, r, f["peso"] * math.sin(f["a"])])
    if any(linha[4] < 0 for linha in linhas):
        mem.premissa("Normal efetiva negativa em alguma fatia: parcela de atrito considerada nula nela")
    mem.tabela(
        "Fellenius – cálculo por fatia",
        [("b", "m"), ("W", "kN/m"), ("α", "grau"), ("l = b/cos α", "m"), ("N' = W·cos α − u·l", "kN/m"),
         ("R = c'·l + N'·tan φ'", "kN/m"), ("S = W·sen α", "kN/m")],
        linhas,
    )
    sr = mem.passo("Soma dos esforços resistentes", "ΣR = Σ [c'·l + (W·cos α − u·l)·tan φ']", "ΣR", resistente, "kN/m")
    ss = _momento_atuante(fatias, mem)
    fs = mem.passo("Fator de segurança (Fellenius)", "FS = ΣR / ΣS", f"FS = {fmt(sr)} / {fmt(ss)}", sr / ss, "-")
    sev = classificar_fs(fs, fs_min)
    _parecer_fs(mem, fs, fs_min, sev, "Fellenius")
    return [resultado(mem, "estabilidade.talude_fellenius.fs", "FS (Fellenius)", fs, "-", FONTE_TALUDE, sev, fs_min)]


@calculo(
    "estabilidade.talude_bishop",
    "FS de talude pelo método de Bishop simplificado",
    FONTE_TALUDE,
    (FATIAS,),
    limites=(FS_MIN_TALUDE,),
)
def talude_bishop(e, mem: Memoria):
    fs_min = mem.limite("fs_min_talude")
    fatias = _fatias_em_radianos(e["fatias"])
    ss = _momento_atuante(fatias, mem)

    def numeradores(fs: float) -> list[tuple[float, float]]:
        """(m_α, parcela resistente) por fatia para um FS tentativo."""
        saida = []
        for f in fatias:
            m_alfa = math.cos(f["a"]) + math.sin(f["a"]) * f["tphi"] / fs
            efetivo = max(f["peso"] - f["poropressao"] * f["largura"], 0.0)
            saida.append((m_alfa, (f["coesao"] * f["largura"] + efetivo * f["tphi"]) / m_alfa))
        return saida

    # Estimativa inicial: Fellenius sem poropressão negativa (converge rapidamente).
    fs = sum(
        f["coesao"] * f["largura"] / math.cos(f["a"]) + max(f["peso"] * math.cos(f["a"]) - f["poropressao"] * f["largura"] / math.cos(f["a"]), 0) * f["tphi"]
        for f in fatias
    ) / ss
    fs = max(fs, 0.1)
    for iteracao in range(1, _BISHOP_MAX_ITERACOES + 1):
        parcelas = numeradores(fs)
        if any(m <= 0 for m, _ in parcelas):
            raise erro_campo("fatias", "m_α ≤ 0 em alguma fatia: Bishop não se aplica a esta superfície (base muito íngreme contra o movimento)")
        novo = sum(p for _, p in parcelas) / ss
        if abs(novo - fs) < _BISHOP_TOLERANCIA:
            fs = novo
            break
        fs = novo
    else:
        raise erro_campo("fatias", f"Bishop não convergiu em {_BISHOP_MAX_ITERACOES} iterações")

    parcelas = numeradores(fs)
    if any(m < _BISHOP_M_ALFA_MINIMO for m, _ in parcelas):
        mem.premissa(f"m_α < {fmt(_BISHOP_M_ALFA_MINIMO)} em alguma fatia: resultado sensível, conferir a geometria da superfície")
    if any(f["peso"] - f["poropressao"] * f["largura"] < 0 for f in fatias):
        mem.premissa("Peso efetivo negativo em alguma fatia (u·b > W): parcela de atrito considerada nula nela")
    mem.tabela(
        "Bishop simplificado – cálculo por fatia (FS final)",
        [("b", "m"), ("W", "kN/m"), ("α", "grau"), ("m_α = cos α + sen α·tan φ'/FS", "-"),
         ("[c'·b + (W − u·b)·tan φ'] / m_α", "kN/m"), ("S = W·sen α", "kN/m")],
        [[f["largura"], f["peso"], f["alfa"], m, p, f["peso"] * math.sin(f["a"])] for f, (m, p) in zip(fatias, parcelas)],
    )
    sr = mem.passo(
        "Soma dos esforços resistentes (FS final)",
        "ΣR = Σ {[c'·b + (W − u·b)·tan φ'] / m_α}",
        "ΣR",
        sum(p for _, p in parcelas),
        "kN/m",
    )
    fs = mem.passo(f"Fator de segurança (Bishop, {iteracao} iterações)", "FS = ΣR / ΣS", f"FS = {fmt(sr)} / {fmt(ss)}", sr / ss, "-")
    sev = classificar_fs(fs, fs_min)
    _parecer_fs(mem, fs, fs_min, sev, "Bishop simplificado")
    return [resultado(mem, "estabilidade.talude_bishop.fs", "FS (Bishop simplificado)", fs, "-", FONTE_TALUDE, sev, fs_min)]


# --- barragens de gravidade -------------------------------------------------------------

PESO = Entrada("peso", "Peso próprio da barragem por metro (P)", "kN/m", minimo=0, minimo_inclusivo=False)
EMPUXO = Entrada("empuxo", "Empuxo horizontal da água por metro (E) – ver hidrostatica.empuxo", "kN/m", minimo=0, minimo_inclusivo=False)
SUBPRESSAO = Entrada("subpressao", "Subpressão por metro (U) – ver hidrostatica.subpressao", "kN/m", minimo=0, padrao=0.0)


@calculo(
    "estabilidade.gravidade_deslizamento",
    "Barragem de gravidade: segurança contra escorregamento",
    FONTE_GRAVIDADE,
    (
        PESO,
        EMPUXO,
        SUBPRESSAO,
        Entrada("coeficiente_atrito", "Coeficiente de atrito base–fundação (f)", minimo=0, minimo_inclusivo=False, padrao=0.75),
    ),
    limites=(FS_MIN_DESLIZAMENTO,),
)
def gravidade_deslizamento(e, mem: Memoria):
    p, emp, u, f = e["peso"], e["empuxo"], e["subpressao"], e["coeficiente_atrito"]
    n = mem.limite("fs_min_deslizamento")
    normal = mem.passo("Força normal efetiva na base", "N = P − U", f"N = {fmt(p)} − {fmt(u)}", p - u, "kN/m")
    if normal <= 0:
        mem.conclusao("Subpressão maior ou igual ao peso: barragem sujeita a flutuação.")
        return [resultado(mem, "estabilidade.gravidade_deslizamento.fs", "FS contra escorregamento", 0.0, "-", FONTE_GRAVIDADE, Severidade.CRITICO, n)]
    atrito = mem.passo("Resistência por atrito", "F = f · N", f"F = {fmt(f)} · {fmt(normal)}", f * normal, "kN/m")
    fs = mem.passo("Fator de segurança contra escorregamento", "FS = f · N / E", f"FS = {fmt(atrito)} / {fmt(emp)}", atrito / emp, "-")
    p_min = mem.passo(
        "Peso mínimo para atender ao critério",
        "P_mín = E · n / f + U",
        f"P_mín = {fmt(emp)} · {fmt(n)} / {fmt(f)} + {fmt(u)}",
        emp * n / f + u,
        "kN/m",
    )
    sev = classificar_fs(fs, n)
    if sev is Severidade.OK:
        mem.conclusao(f"FS = {fmt(round(fs, 2))} ≥ {fmt(n)}: atende (P·f ≥ E·n).")
    else:
        mem.conclusao(f"FS = {fmt(round(fs, 2))} < {fmt(n)}: não atende; peso necessário ≥ {fmt(round(p_min, 1))} kN/m.")
    return [
        resultado(mem, "estabilidade.gravidade_deslizamento.fs", "FS contra escorregamento", fs, "-", FONTE_GRAVIDADE, sev, n),
        resultado(mem, "estabilidade.gravidade_deslizamento.peso_minimo", "Peso mínimo para o critério", p_min, "kN/m", FONTE_GRAVIDADE),
    ]


@calculo(
    "estabilidade.gravidade_resultante",
    "Barragem de gravidade: posição da resultante e tensões na base (terço médio)",
    FONTE_GRAVIDADE,
    (
        Entrada("largura_base", "Largura da base (B)", "m", minimo=0, minimo_inclusivo=False),
        PESO,
        Entrada("braco_peso", "Distância do centro de gravidade ao pé de montante (x_P)", "m", minimo=0),
        EMPUXO,
        Entrada("altura_empuxo", "Altura de aplicação do empuxo acima da base (y_E; h/3 no paramento vertical)", "m", minimo=0),
        SUBPRESSAO,
        Entrada("braco_subpressao", "Distância da subpressão ao pé de montante (x_U)", "m", minimo=0, padrao=0.0),
        Entrada("empuxo_vertical", "Peso da água sobre o paramento inclinado (Ev), opcional", "kN/m", minimo=0, padrao=0.0),
        Entrada("braco_empuxo_vertical", "Distância de Ev ao pé de montante (x_Ev)", "m", minimo=0, padrao=0.0),
    ),
)
def gravidade_resultante(e, mem: Memoria):
    b = e["largura_base"]
    p, xp = e["peso"], e["braco_peso"]
    emp, ye = e["empuxo"], e["altura_empuxo"]
    u, xu = e["subpressao"], e["braco_subpressao"]
    ev, xev = e["empuxo_vertical"], e["braco_empuxo_vertical"]
    for campo, valor in (("braco_peso", xp), ("braco_subpressao", xu), ("braco_empuxo_vertical", xev)):
        if valor > b:
            raise erro_campo(campo, f"não pode exceder a largura da base ({fmt(b)} m)", "FORA_DO_INTERVALO")

    normal = mem.passo("Resultante vertical na base", "N = P + Ev − U", f"N = {fmt(p)} + {fmt(ev)} − {fmt(u)}", p + ev - u, "kN/m")
    if normal <= 0:
        mem.conclusao("Subpressão maior ou igual às cargas verticais: barragem sujeita a flutuação.")
        return [resultado(mem, "estabilidade.gravidade_resultante.normal", "Resultante vertical", normal, "kN/m", FONTE_GRAVIDADE, Severidade.CRITICO)]

    momento = mem.passo(
        "Momento em relação ao pé de montante",
        "M = P·x_P + Ev·x_Ev − U·x_U + E·y_E",
        f"M = {fmt(p)}·{fmt(xp)} + {fmt(ev)}·{fmt(xev)} − {fmt(u)}·{fmt(xu)} + {fmt(emp)}·{fmt(ye)}",
        p * xp + ev * xev - u * xu + emp * ye,
        "kN·m/m",
    )
    x_r = mem.passo("Ponto em que a resultante corta a base", "x_R = M / N", f"x_R = {fmt(momento)} / {fmt(normal)}", momento / normal, "m")
    exc = mem.passo("Excentricidade em relação ao centro da base", "e = x_R − B/2", f"e = {fmt(x_r)} − {fmt(b)}/2", x_r - b / 2, "m")
    sigma_m = mem.passo(
        "Tensão normal no pé de montante",
        "σ_m = N/B · (1 − 6e/B)",
        f"σ_m = {fmt(normal)}/{fmt(b)} · (1 − 6·{fmt(exc)}/{fmt(b)})",
        normal / b * (1 - 6 * exc / b),
        "kPa",
    )
    sigma_j = mem.passo(
        "Tensão normal no pé de jusante",
        "σ_j = N/B · (1 + 6e/B)",
        f"σ_j = {fmt(normal)}/{fmt(b)} · (1 + 6·{fmt(exc)}/{fmt(b)})",
        normal / b * (1 + 6 * exc / b),
        "kPa",
    )

    if b / 3 <= x_r <= 2 * b / 3:
        sev = Severidade.OK
        mem.conclusao(f"Resultante no terço médio (x_R = {fmt(round(x_r, 2))} m entre {fmt(round(b / 3, 2))} e {fmt(round(2 * b / 3, 2))} m): base inteiramente comprimida.")
    elif 0 <= x_r <= b:
        sev = Severidade.ALERTA
        mem.conclusao("Resultante fora do terço médio: tração em parte da base; a fórmula linear de tensões deixa de valer no trecho tracionado.")
    else:
        sev = Severidade.CRITICO
        mem.conclusao("Resultante fora da base: tombamento.")

    fonte = FONTE_GRAVIDADE
    return [
        resultado(mem, "estabilidade.gravidade_resultante.normal", "Resultante vertical", normal, "kN/m", fonte),
        resultado(mem, "estabilidade.gravidade_resultante.posicao", "Posição da resultante (a partir do pé de montante)", x_r, "m", fonte, sev),
        resultado(mem, "estabilidade.gravidade_resultante.excentricidade", "Excentricidade (limite B/6)", exc, "m", fonte, sev, b / 6),
        resultado(mem, "estabilidade.gravidade_resultante.tensao_montante", "Tensão no pé de montante", sigma_m, "kPa", fonte),
        resultado(mem, "estabilidade.gravidade_resultante.tensao_jusante", "Tensão no pé de jusante", sigma_j, "kPa", fonte),
    ]
