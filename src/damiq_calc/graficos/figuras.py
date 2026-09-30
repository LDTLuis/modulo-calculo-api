"""Figuras dos relatórios.

Estilo (diretrizes de visualização do projeto): uma série por eixo, linha de 2 px com
marcadores, grade em linha fina e recessiva, texto sempre em tinta neutra. Limites de alerta
usam as cores de status reservadas **e** rótulo em texto — a cor nunca carrega o significado
sozinha. Nunca há eixo duplo: grandezas de escalas diferentes viram painéis lado a lado.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from damiq_calc.core.calculo import fmt
from damiq_calc.medicoes.modelo import FlagQualidade, Medicao
from damiq_calc.monitoramento import LimitesAlerta

FORMATOS = ("png", "svg")

# Paleta de referência (superfície clara; o relatório é impresso)
SUPERFICIE = "#fcfcfb"
TINTA = "#0b0b0b"
TINTA_SECUNDARIA = "#52514e"
TINTA_MUDA = "#898781"
GRADE = "#e1e0d9"
EIXO = "#c3c2b7"
SERIE = "#2a78d6"
STATUS = {"aviso": "#fab219", "alerta": "#ec835a", "critico": "#d03b3b"}
NOMES_NIVEIS = {"aviso": "Aviso", "alerta": "Alerta", "critico": "Crítico"}
NOMES_TIPOS = {"nivel": "nível", "pressao": "pressão", "vazao": "vazão", "deslocamento": "deslocamento"}


def _figura(largura: float = 8.0, altura: float = 4.0, paineis: int = 1):
    from matplotlib.figure import Figure  # import tardio: só quem gera gráfico paga o custo

    fig = Figure(figsize=(largura, altura), dpi=150, facecolor=SUPERFICIE)
    eixos = fig.subplots(1, paineis, squeeze=False)[0]
    for ax in eixos:
        ax.set_facecolor(SUPERFICIE)
        ax.grid(True, color=GRADE, linewidth=0.6)
        ax.set_axisbelow(True)
        for lado in ("top", "right"):
            ax.spines[lado].set_visible(False)
        for lado in ("left", "bottom"):
            ax.spines[lado].set_color(EIXO)
        ax.tick_params(colors=TINTA_MUDA, labelsize=8)
    return fig, eixos


def _salvar(fig, caminho: Path, margem_direita: float = 0.0) -> Path:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout(rect=(0, 0, 1 - margem_direita, 1))
    fig.savefig(caminho, facecolor=SUPERFICIE)
    return caminho


def serie_temporal(
    medicoes: Sequence[Medicao],
    caminho: Path,
    *,
    limites: LimitesAlerta | None = None,
    titulo: str | None = None,
) -> Path:
    """Série temporal de um sensor, com linhas de limite e leituras suspeitas destacadas."""
    if not medicoes:
        raise ValueError("série vazia")
    ordenadas = sorted(medicoes, key=lambda m: m.timestamp)
    sensor, unidade = ordenadas[0].sensor, ordenadas[0].unidade
    x = [m.timestamp for m in ordenadas]
    y = [m.valor for m in ordenadas]

    fig, (ax,) = _figura()

    ax.plot(x, y, color=SERIE, linewidth=2, marker="o", markersize=5, markeredgecolor=SUPERFICIE, markeredgewidth=1.5, zorder=3)
    suspeitas = [(m.timestamp, m.valor) for m in ordenadas if FlagQualidade.FORA_FAIXA_PLAUSIVEL in m.flags]
    if suspeitas:
        sx, sy = zip(*suspeitas)
        ax.plot(sx, sy, linestyle="none", marker="o", markersize=9, markerfacecolor=SUPERFICIE, markeredgecolor=TINTA, markeredgewidth=1.5, zorder=4, label="Leitura fora da faixa plausível")
        ax.legend(loc="upper left", fontsize=8, frameon=False, labelcolor=TINTA_SECUNDARIA)

    margem = 0.0
    if limites is not None:
        ambos = limites.acima is not None and limites.abaixo is not None
        for direcao, niveis in (("acima", limites.acima), ("abaixo", limites.abaixo)):
            if niveis is None:
                continue
            for nome in ("aviso", "alerta", "critico"):
                valor = getattr(niveis, nome)
                if valor is None:
                    continue
                ax.axhline(valor, color=STATUS[nome], linewidth=1.5, linestyle=(0, (6, 3)), zorder=2)
                # rótulo na margem direita, fora da área de dados: nunca colide com a série
                sufixo = f" ({direcao})" if ambos else ""
                ax.annotate(
                    f"{NOMES_NIVEIS[nome]}{sufixo} {fmt(valor)} {unidade}",
                    xy=(1, valor),
                    xycoords=("axes fraction", "data"),
                    xytext=(6, 0),
                    textcoords="offset points",
                    ha="left",
                    va="center",
                    fontsize=7.5,
                    color=TINTA_SECUNDARIA,
                    annotation_clip=False,
                )
                margem = 0.14 if ambos else 0.12

    from matplotlib.dates import DateFormatter

    tipo = NOMES_TIPOS.get(ordenadas[0].tipo.value, ordenadas[0].tipo.value)
    ax.set_title(titulo or f"{sensor} – {tipo}", loc="left", fontsize=11, color=TINTA)
    ax.set_ylabel(unidade, color=TINTA_SECUNDARIA, fontsize=9)
    ax.xaxis.set_major_formatter(DateFormatter("%d/%m/%Y"))
    fig.autofmt_xdate()
    return _salvar(fig, caminho, margem)


def curva_cota_area_volume(pontos: Sequence[tuple[float, float, float]], caminho: Path, *, titulo: str | None = None) -> Path:
    """Curvas cota × volume e cota × área em painéis lado a lado (escalas diferentes → sem eixo duplo).

    `pontos` = [(cota, área m², volume acumulado m³), ...].
    """
    if len(pontos) < 2:
        raise ValueError("a curva precisa de ao menos dois pontos")
    ordenados = sorted(pontos)
    cotas = [p[0] for p in ordenados]
    fig, (ax_v, ax_a) = _figura(largura=9.0, altura=4.2, paineis=2)
    ax_v.plot([p[2] for p in ordenados], cotas, color=SERIE, linewidth=2, marker="o", markersize=5, markeredgecolor=SUPERFICIE, markeredgewidth=1.5)
    ax_v.set_xlabel("Volume acumulado (m³)", color=TINTA_SECUNDARIA, fontsize=9)
    ax_v.set_ylabel("Cota (m)", color=TINTA_SECUNDARIA, fontsize=9)
    ax_v.set_title("Cota × volume", loc="left", fontsize=10, color=TINTA)
    ax_a.plot([p[1] for p in ordenados], cotas, color=SERIE, linewidth=2, marker="o", markersize=5, markeredgecolor=SUPERFICIE, markeredgewidth=1.5)
    ax_a.set_xlabel("Área do espelho d'água (m²)", color=TINTA_SECUNDARIA, fontsize=9)
    ax_a.set_title("Cota × área", loc="left", fontsize=10, color=TINTA)
    ax_a.sharey(ax_v)
    if titulo:
        fig.suptitle(titulo, x=0.01, ha="left", fontsize=11, color=TINTA)
    return _salvar(fig, caminho)
