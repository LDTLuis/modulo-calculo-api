"""Cálculos de emergência (PAE).

O motor não modela a ruptura (Saint-Venant/HEC-RAS): recebe os resultados do estudo de
ruptura já feito — distância × tempo de chegada da onda — e aplica os critérios do PAE.
"""

from __future__ import annotations

from damiq_calc.core.calculo import Entrada, EntradaTabela, Limite, Memoria, calculo, erro_campo, fmt, resultado
from damiq_calc.core.resultado import Severidade

from .niveis import FONTE as FONTE_NIVEIS
from .niveis import nivel_de_resposta

FONTE_ZAS = "PAE João Leite, Anexo – Zona de Autossalvamento (critério do guia da ANA)"

ZAS_DISTANCIA_MAX = Limite("zas_distancia_max_km", "Extensão máxima da ZAS a jusante (km)", 10.0)
ZAS_TEMPO_CHEGADA = Limite("zas_tempo_chegada_min", "Tempo de chegada da onda que delimita a ZAS (min)", 30.0)


@calculo(
    "emergencia.nivel_resposta",
    "Nível de resposta do PAE a partir da severidade",
    FONTE_NIVEIS,
    (Entrada("severidade", "Severidade: 0 = OK, 1 = AVISO, 2 = ALERTA, 3 = CRITICO", minimo=0, maximo=3, inteiro=True),),
)
def nivel_resposta(e, mem: Memoria):
    severidade = Severidade(int(e["severidade"]))
    nivel = nivel_de_resposta(severidade)
    mem.conclusao(f"{nivel.rotulo}: {nivel.situacao}")
    for acao in nivel.acoes:
        mem.conclusao(f"Ação: {acao}")
    return [
        resultado(mem, "emergencia.nivel_resposta.nivel", "Nível de resposta", float(nivel.nivel), "-", FONTE_NIVEIS, severidade, rotulo=nivel.rotulo)
    ]


@calculo(
    "emergencia.zas",
    "Extensão da Zona de Autossalvamento (ZAS)",
    FONTE_ZAS,
    (
        EntradaTabela(
            "secoes",
            "Seções do estudo de ruptura: distância à barragem e tempo de chegada da onda",
            (
                Entrada("distancia", "Distância a jusante da barragem", "km", minimo=0),
                Entrada("tempo_chegada", "Tempo de chegada da onda de ruptura", "min", minimo=0),
            ),
            min_linhas=2,
        ),
    ),
    limites=(ZAS_DISTANCIA_MAX, ZAS_TEMPO_CHEGADA),
)
def zas(e, mem: Memoria):
    d_max = mem.limite("zas_distancia_max_km")
    t_zas = mem.limite("zas_tempo_chegada_min")
    secoes = sorted(e["secoes"], key=lambda s: s["distancia"])
    for a, b in zip(secoes, secoes[1:]):
        if b["distancia"] == a["distancia"]:
            raise erro_campo("secoes", f"distância {fmt(b['distancia'])} km repetida")
        if b["tempo_chegada"] < a["tempo_chegada"]:
            raise erro_campo("secoes", "o tempo de chegada deve crescer com a distância")

    d_tempo = None
    for a, b in zip(secoes, secoes[1:]):
        if a["tempo_chegada"] <= t_zas <= b["tempo_chegada"]:
            if b["tempo_chegada"] == a["tempo_chegada"]:
                d_tempo = a["distancia"]
            else:
                d_tempo = mem.passo(
                    f"Distância alcançada pela onda em {fmt(t_zas)} min (interpolação)",
                    "d = d0 + (d1 − d0)·(t − t0)/(t1 − t0)",
                    f"d = {fmt(a['distancia'])} + ({fmt(b['distancia'])} − {fmt(a['distancia'])})·({fmt(t_zas)} − {fmt(a['tempo_chegada'])})/({fmt(b['tempo_chegada'])} − {fmt(a['tempo_chegada'])})",
                    a["distancia"] + (b["distancia"] - a["distancia"]) * (t_zas - a["tempo_chegada"]) / (b["tempo_chegada"] - a["tempo_chegada"]),
                    "km",
                )
            break

    severidade = Severidade.OK
    if d_tempo is None and secoes[0]["tempo_chegada"] > t_zas:
        d_tempo = secoes[0]["distancia"]
        mem.premissa(f"A primeira seção já é alcançada após {fmt(t_zas)} min: ZAS limitada à primeira seção do estudo")
    elif d_tempo is None:
        ultima = secoes[-1]["distancia"]
        if ultima < d_max:
            severidade = Severidade.AVISO
            mem.premissa(f"O estudo termina em {fmt(ultima)} km sem atingir {fmt(t_zas)} min: estender o estudo de ruptura")
        d_tempo = ultima

    extensao = mem.passo(
        "Extensão da ZAS",
        f"ZAS = mín({fmt(d_max)} km; distância alcançada em {fmt(t_zas)} min)",
        f"ZAS = mín({fmt(d_max)}; {fmt(d_tempo)})",
        min(d_max, d_tempo),
        "km",
    )
    criterio = "distância máxima" if extensao == d_max and d_tempo > d_max else f"tempo de chegada de {fmt(t_zas)} min"
    mem.conclusao(f"ZAS até {fmt(round(extensao, 2))} km a jusante (governada pelo critério de {criterio}).")
    return [resultado(mem, "emergencia.zas.extensao", "Extensão da ZAS a jusante", extensao, "km", FONTE_ZAS, severidade)]
