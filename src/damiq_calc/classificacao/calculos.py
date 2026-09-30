"""Classificação regulatória de barragens.

Fontes: Apostila BCST (AP) – Notas 01 e 08: Lei 12.334/2010 (PNSB), Res. CNRH 143/2012
(matriz CRI × DPA), IN SEMAD-GO 01/2020 (cadastramento por grupos) e periodicidade da
Revisão Periódica de Segurança (RPSB).

As tabelas de pontuação dos itens de CT, EC, PS e DPA estão como imagens na apostila; aqui o
usuário (ou a tela da Central) informa as pontuações já apuradas. As faixas de corte são
critérios configuráveis (`limites_calculo`) e devem ser conferidas com as tabelas da apostila.
"""

from __future__ import annotations

from damiq_calc.core.calculo import Entrada, Limite, Memoria, calculo, erro_campo, fmt, resultado
from damiq_calc.core.resultado import Severidade

FONTE_PNSB = "AP, Nota 01 – Lei 12.334/2010 (PNSB) e IN SEMAD-GO 01/2020"
FONTE_MATRIZ = "AP, Nota 08 – Res. CNRH 143/2012: matriz de classificação CRI × DPA"

CRI_ALTO = Limite("cri_limite_alto", "CRI a partir do qual a categoria de risco é ALTA", 60.0)
CRI_MEDIO = Limite("cri_limite_medio", "CRI acima do qual a categoria de risco é MÉDIA", 35.0)
EC_ITEM_ALTO = Limite("ec_item_risco_alto", "Pontuação de um item de EC que torna o risco ALTO automaticamente", 10.0)
DPA_ALTO = Limite("dpa_limite_alto", "DPA a partir do qual o dano potencial é ALTO", 16.0)
DPA_MEDIO = Limite("dpa_limite_medio", "DPA acima do qual o dano potencial é MÉDIO", 10.0)

ALTURA_PNSB_M = 15.0
VOLUME_PNSB_M3 = 3e6

# Matriz da apostila (Res. CNRH 143/2012): linha = categoria de risco, coluna = DPA
MATRIZ = {
    "ALTO": {"ALTO": "A", "MÉDIO": "B", "BAIXO": "C"},
    "MÉDIO": {"ALTO": "A", "MÉDIO": "C", "BAIXO": "D"},
    "BAIXO": {"ALTO": "A", "MÉDIO": "D", "BAIXO": "D"},
}
# Periodicidade da RPSB por classe (anos)
PERIODICIDADE_RPSB = {"A": 5, "B": 7, "C": 10, "D": 12}
INDICE_CLASSE = {"A": 1, "B": 2, "C": 3, "D": 4}


@calculo(
    "classificacao.enquadramento_pnsb",
    "Enquadramento na Política Nacional de Segurança de Barragens e grupo de cadastramento",
    FONTE_PNSB,
    (
        Entrada("altura_macico", "Altura do maciço, do ponto mais baixo da fundação à crista", "m", minimo=0),
        Entrada("capacidade", "Capacidade total do reservatório", "m3", minimo=0),
        Entrada("residuos_perigosos", "Reservatório contém resíduos perigosos? (1 = sim, 0 = não)", minimo=0, maximo=1, inteiro=True, padrao=0),
        Entrada("dpa", "Pontuação de DPA, se já apurada (opcional)", minimo=0, opcional=True),
    ),
    limites=(DPA_MEDIO,),
)
def enquadramento_pnsb(e, mem: Memoria):
    h, v, residuos, dpa = e["altura_macico"], e["capacidade"], e["residuos_perigosos"], e["dpa"]
    criterios = []
    if h >= ALTURA_PNSB_M:
        criterios.append(f"altura {fmt(h)} m ≥ 15 m")
    if v >= VOLUME_PNSB_M3:
        criterios.append(f"capacidade {fmt(v / 1e6)} hm³ ≥ 3 hm³")
    if residuos:
        criterios.append("contém resíduos perigosos")
    if dpa is not None:
        limite_medio = mem.limite("dpa_limite_medio")
        if dpa > limite_medio:
            criterios.append(f"DPA médio ou alto ({fmt(dpa)} > {fmt(limite_medio)})")
    enquadrada = bool(criterios)
    if enquadrada:
        mem.conclusao("Enquadrada na PNSB: " + "; ".join(criterios) + ".")
    else:
        mem.conclusao("Não se enquadra nos critérios da PNSB (Lei 12.334/2010, art. 1º); cadastro estadual continua obrigatório em Goiás.")
        if dpa is None:
            mem.premissa("DPA não informado: o enquadramento por dano potencial médio/alto não foi avaliado")

    if h >= ALTURA_PNSB_M or v >= VOLUME_PNSB_M3:
        grupo, prazo = 1, "até 30/09/2020"
    elif h >= 5 or v >= 1e6:
        grupo, prazo = 2, "até 31/10/2020"
    else:
        grupo, prazo = 3, "até 31/12/2020"
    mem.conclusao(f"Cadastramento SEMAD-GO: grupo {grupo} (prazo {prazo}, IN 01/2020).")
    return [
        resultado(mem, "classificacao.enquadramento_pnsb.enquadrada", "Enquadrada na PNSB", float(enquadrada), "-", FONTE_PNSB, rotulo="SIM" if enquadrada else "NÃO"),
        resultado(mem, "classificacao.enquadramento_pnsb.grupo_semad", "Grupo de cadastramento SEMAD-GO", float(grupo), "-", FONTE_PNSB, rotulo=f"Grupo {grupo}"),
    ]


@calculo(
    "classificacao.risco",
    "Categoria de risco (CRI), dano potencial (DPA), classe e periodicidade da RPSB",
    FONTE_MATRIZ,
    (
        Entrada("ct", "Pontuação de Características Técnicas (CT)", minimo=0),
        Entrada("ec", "Pontuação de Estado de Conservação (EC)", minimo=0),
        Entrada("ps", "Pontuação de Plano de Segurança (PS)", minimo=0),
        Entrada("ec_item_maximo", "Maior pontuação individual entre os itens de EC", minimo=0, padrao=0),
        Entrada("dpa", "Pontuação de Dano Potencial Associado (DPA)", minimo=0),
    ),
    limites=(CRI_ALTO, CRI_MEDIO, EC_ITEM_ALTO, DPA_ALTO, DPA_MEDIO),
)
def risco(e, mem: Memoria):
    ct, ec, ps, ec_max, dpa = e["ct"], e["ec"], e["ps"], e["ec_item_maximo"], e["dpa"]
    if ec_max > ec:
        raise erro_campo("ec_item_maximo", "não pode exceder a pontuação total de EC", "FORA_DO_INTERVALO")
    cri_alto, cri_medio = mem.limite("cri_limite_alto"), mem.limite("cri_limite_medio")
    ec_item_alto = mem.limite("ec_item_risco_alto")
    dpa_alto, dpa_medio = mem.limite("dpa_limite_alto"), mem.limite("dpa_limite_medio")

    cri = mem.passo("Categoria de risco", "CRI = CT + EC + PS", f"CRI = {fmt(ct)} + {fmt(ec)} + {fmt(ps)}", ct + ec + ps, "-")
    if ec_max >= ec_item_alto:
        cat_risco, sev_risco = "ALTO", Severidade.CRITICO
        mem.conclusao(f"Item de EC com pontuação {fmt(ec_max)}: categoria de risco ALTA automaticamente — intervenção imediata e inspeção especial (AP).")
    elif cri >= cri_alto:
        cat_risco, sev_risco = "ALTO", Severidade.ALERTA
    elif cri > cri_medio:
        cat_risco, sev_risco = "MÉDIO", Severidade.AVISO
    else:
        cat_risco, sev_risco = "BAIXO", Severidade.OK

    if dpa >= dpa_alto:
        cat_dpa = "ALTO"
    elif dpa > dpa_medio:
        cat_dpa = "MÉDIO"
    else:
        cat_dpa = "BAIXO"

    classe = MATRIZ[cat_risco][cat_dpa]
    anos = PERIODICIDADE_RPSB[classe]
    mem.tabela(
        "Matriz de classificação (Res. CNRH 143/2012) – linha: categoria de risco; coluna: DPA",
        [("risco \\ DPA", "-"), ("ALTO", "-"), ("MÉDIO", "-"), ("BAIXO", "-")],
        [[linha, *MATRIZ[linha].values()] for linha in MATRIZ],
    )
    mem.conclusao(f"CRI = {fmt(cri)} (risco {cat_risco}); DPA = {fmt(dpa)} ({cat_dpa}) → classe {classe}; RPSB a cada {anos} anos.")
    return [
        resultado(mem, "classificacao.risco.cri", "Categoria de risco (CRI)", cri, "-", FONTE_MATRIZ, sev_risco, rotulo=cat_risco),
        resultado(mem, "classificacao.risco.dpa", "Dano potencial associado (DPA)", dpa, "-", FONTE_MATRIZ, rotulo=cat_dpa),
        resultado(mem, "classificacao.risco.classe", "Classe da barragem", float(INDICE_CLASSE[classe]), "-", FONTE_MATRIZ, rotulo=classe),
        resultado(mem, "classificacao.risco.periodicidade_rpsb", "Periodicidade da Revisão Periódica de Segurança", float(anos), "anos", FONTE_MATRIZ, rotulo=f"a cada {anos} anos"),
    ]
