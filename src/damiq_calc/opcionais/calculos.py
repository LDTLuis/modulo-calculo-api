"""Cálculos opcionais [LIT].

Não constam na apostila BCST nem no PAE de referência; entram como apoio e cada resultado
registra essa condição nas premissas.
"""

from __future__ import annotations

from damiq_calc.core.calculo import Entrada, Memoria, calculo, fmt, resultado
from damiq_calc.core.resultado import Severidade

FONTE_FRANCIS = "[LIT] Francis – vertedor retangular de parede delgada, sem contrações laterais"
FONTE_THOMSON = "[LIT] Thomson – vertedor triangular de 90°"
FONTE_FAO56 = "[LIT] FAO-56 (Allen et al., 1998) – Penman-Monteith, passo diário"
FONTE_BALANCO = "[LIT] Balanço hídrico do reservatório (conservação de volume)"
FONTE_FROEHLICH = "[LIT] Froehlich (1995) – vazão de pico de ruptura por regressão"

_PREMISSA_LIT = "Cálculo da literatura técnica, fora do material de referência do professor"


@calculo(
    "opcionais.vertedor_retangular",
    "Vazão em vertedor retangular (Francis)",
    FONTE_FRANCIS,
    (
        Entrada("largura", "Largura da soleira (L)", "m", minimo=0, minimo_inclusivo=False),
        Entrada("carga", "Carga hidráulica sobre a soleira (H)", "m", minimo=0),
        Entrada("coeficiente", "Coeficiente de descarga (C, SI)", minimo=0, minimo_inclusivo=False, padrao=1.838),
    ),
)
def vertedor_retangular(e, mem: Memoria):
    mem.premissa(_PREMISSA_LIT)
    largura, h, c = e["largura"], e["carga"], e["coeficiente"]
    q = mem.passo("Vazão", "Q = C · L · H^1,5", f"Q = {fmt(c)} · {fmt(largura)} · {fmt(h)}^1,5", c * largura * h**1.5, "m3/s")
    return [resultado(mem, "opcionais.vertedor_retangular.vazao", "Vazão no vertedor", q, "m3/s", FONTE_FRANCIS)]


@calculo(
    "opcionais.vertedor_triangular",
    "Vazão em vertedor triangular de 90° (Thomson) – medidores de vazão de drenagem",
    FONTE_THOMSON,
    (
        Entrada("carga", "Carga hidráulica sobre o vértice (H)", "m", minimo=0),
        Entrada("coeficiente", "Coeficiente (SI)", minimo=0, minimo_inclusivo=False, padrao=1.4),
    ),
)
def vertedor_triangular(e, mem: Memoria):
    mem.premissa(_PREMISSA_LIT)
    h, c = e["carga"], e["coeficiente"]
    q = mem.passo("Vazão", "Q = C · H^2,5", f"Q = {fmt(c)} · {fmt(h)}^2,5", c * h**2.5, "m3/s")
    return [resultado(mem, "opcionais.vertedor_triangular.vazao", "Vazão no vertedor", q, "m3/s", FONTE_THOMSON)]


@calculo(
    "opcionais.evapotranspiracao_fao56",
    "Evapotranspiração de referência ET0 (Penman-Monteith FAO-56, diária)",
    FONTE_FAO56,
    (
        Entrada("saldo_radiacao", "Saldo de radiação Rn, em MJ/m²/dia"),
        Entrada("fluxo_calor_solo", "Fluxo de calor no solo G, em MJ/m²/dia (≈ 0 no passo diário)", padrao=0.0),
        Entrada("temperatura", "Temperatura média do ar T, em °C", minimo=-50, maximo=60),
        Entrada("vento_2m", "Velocidade do vento a 2 m (u2)", "m/s", minimo=0),
        Entrada("pressao_saturacao", "Pressão de saturação de vapor (es)", "kPa", minimo=0),
        Entrada("pressao_real", "Pressão real de vapor (ea)", "kPa", minimo=0),
        Entrada("declividade_curva", "Declividade da curva de pressão de vapor Δ, em kPa/°C", minimo=0, minimo_inclusivo=False),
        Entrada("constante_psicrometrica", "Constante psicrométrica γ, em kPa/°C (0,067 ao nível do mar)", minimo=0, minimo_inclusivo=False, padrao=0.067),
    ),
)
def evapotranspiracao_fao56(e, mem: Memoria):
    mem.premissa(_PREMISSA_LIT)
    rn, g, t, u2 = e["saldo_radiacao"], e["fluxo_calor_solo"], e["temperatura"], e["vento_2m"]
    es, ea, delta, gama = e["pressao_saturacao"], e["pressao_real"], e["declividade_curva"], e["constante_psicrometrica"]
    if ea > es:
        mem.premissa("ea > es (ar supersaturado): déficit de vapor considerado nulo")
    deficit = max(es - ea, 0.0)
    num = mem.passo(
        "Numerador",
        "N = 0,408·Δ·(Rn − G) + γ·(900/(T + 273))·u2·(es − ea)",
        f"N = 0,408·{fmt(delta)}·({fmt(rn)} − {fmt(g)}) + {fmt(gama)}·(900/({fmt(t)} + 273))·{fmt(u2)}·{fmt(deficit)}",
        0.408 * delta * (rn - g) + gama * (900 / (t + 273)) * u2 * deficit,
        "-",
    )
    den = mem.passo("Denominador", "D = Δ + γ·(1 + 0,34·u2)", f"D = {fmt(delta)} + {fmt(gama)}·(1 + 0,34·{fmt(u2)})", delta + gama * (1 + 0.34 * u2), "-")
    et0 = mem.passo("Evapotranspiração de referência", "ET0 = N / D", f"ET0 = {fmt(num)} / {fmt(den)}", max(num / den, 0.0), "mm/dia")
    return [resultado(mem, "opcionais.evapotranspiracao_fao56.et0", "ET0", et0, "mm/dia", FONTE_FAO56)]


@calculo(
    "opcionais.balanco_hidrico",
    "Balanço hídrico do reservatório no intervalo",
    FONTE_BALANCO,
    (
        Entrada("vazao_afluente", "Vazão afluente média (Qin)", "m3/s", minimo=0),
        Entrada("vazao_efluente", "Vazão efluente média: vertida + captada + descarga (Qout)", "m3/s", minimo=0),
        Entrada("vazao_perdas", "Perdas por infiltração/percolação (Qperdas)", "m3/s", minimo=0, padrao=0.0),
        Entrada("evaporacao", "Evaporação do espelho d'água (E)", "mm/dia", minimo=0, padrao=0.0),
        Entrada("area_espelho", "Área do espelho d'água (A)", "m2", minimo=0, padrao=0.0),
        Entrada("intervalo", "Duração do intervalo (Δt)", "dia", minimo=0, minimo_inclusivo=False),
        Entrada("volume_inicial", "Volume armazenado no início (opcional)", "m3", minimo=0, opcional=True),
    ),
)
def balanco_hidrico(e, mem: Memoria):
    mem.premissa(_PREMISSA_LIT)
    qin, qout, qp = e["vazao_afluente"], e["vazao_efluente"], e["vazao_perdas"]
    evap, area, dias, v0 = e["evaporacao"], e["area_espelho"], e["intervalo"], e["volume_inicial"]
    qevap = mem.passo(
        "Vazão equivalente à evaporação",
        "Qevap = E · A / (1000 · 86400)   (E em mm/dia)",
        f"Qevap = {fmt(evap)} · {fmt(area)} / 86.400.000",
        evap * area / 86_400_000,
        "m3/s",
    )
    dv = mem.passo(
        "Variação de volume",
        "ΔV = (Qin − Qout − Qevap − Qperdas) · Δt",
        f"ΔV = ({fmt(qin)} − {fmt(qout)} − {fmt(qevap)} − {fmt(qp)}) · {fmt(dias)} · 86400",
        (qin - qout - qevap - qp) * dias * 86400,
        "m3",
    )
    resultados = [
        resultado(mem, "opcionais.balanco_hidrico.vazao_evaporacao", "Vazão equivalente à evaporação", qevap, "m3/s", FONTE_BALANCO),
        resultado(mem, "opcionais.balanco_hidrico.variacao_volume", "Variação de volume no intervalo", dv, "m3", FONTE_BALANCO),
    ]
    if v0 is not None:
        sev = Severidade.OK
        if v0 + dv < 0:
            sev = Severidade.ALERTA
            mem.conclusao("O balanço esvazia o reservatório no intervalo: rever vazões ou restringir captações.")
        vf = mem.passo("Volume ao fim do intervalo", "V_fim = máx(0; V_início + ΔV)", f"V_fim = máx(0; {fmt(v0)} + {fmt(dv)})", max(v0 + dv, 0.0), "m3")
        resultados.append(resultado(mem, "opcionais.balanco_hidrico.volume_final", "Volume ao fim do intervalo", vf, "m3", FONTE_BALANCO, sev))
    return resultados


@calculo(
    "opcionais.pico_ruptura_froehlich",
    "Estimativa preliminar da vazão de pico de ruptura (Froehlich, 1995)",
    FONTE_FROEHLICH,
    (
        Entrada("volume_reservatorio", "Volume do reservatório no instante da ruptura (Vw)", "m3", minimo=0, minimo_inclusivo=False),
        Entrada("altura_agua_brecha", "Altura d'água sobre a base da brecha (hw)", "m", minimo=0, minimo_inclusivo=False),
    ),
)
def pico_ruptura_froehlich(e, mem: Memoria):
    mem.premissa(_PREMISSA_LIT)
    mem.premissa("Estimativa preliminar por regressão; o PAE usa modelagem hidrodinâmica (HEC-RAS) com parâmetros Eletrobrás/USACE")
    v, h = e["volume_reservatorio"], e["altura_agua_brecha"]
    qp = mem.passo("Vazão de pico", "Qp = 0,607 · Vw^0,295 · hw^1,24", f"Qp = 0,607 · {fmt(v)}^0,295 · {fmt(h)}^1,24", 0.607 * v**0.295 * h**1.24, "m3/s")
    return [resultado(mem, "opcionais.pico_ruptura_froehlich.vazao_pico", "Vazão de pico estimada", qp, "m3/s", FONTE_FROEHLICH)]
