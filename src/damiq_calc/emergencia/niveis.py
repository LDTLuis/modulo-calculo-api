"""Níveis de resposta do PAE.

Mapeamento proposto (a validar com o professor) entre a severidade do DAMIQ, os níveis do
art. 27 citado na apostila (Nível 0 a 3) e as cores do PAE da Barragem do Ribeirão João Leite,
que adota verde/amarelo/vermelho (o laranja do guia da ANA foi incorporado ao amarelo).
"""

from __future__ import annotations

from dataclasses import dataclass

from damiq_calc.core.resultado import Severidade

FONTE = "AP, Nota 07 – Legislação (art. 27, níveis de resposta); PAE João Leite, Quadro 5.2"


@dataclass(frozen=True, slots=True)
class NivelResposta:
    nivel: int
    cor: str | None
    situacao: str
    acoes: tuple[str, ...]

    @property
    def rotulo(self) -> str:
        return f"Nível {self.nivel}" + (f" – {self.cor}" if self.cor else "")

    def para_dict(self) -> dict:
        return {
            "nivel": self.nivel,
            "cor": self.cor,
            "rotulo": self.rotulo,
            "situacao": self.situacao,
            "acoes": list(self.acoes),
            "fonte": FONTE,
        }


NIVEIS_RESPOSTA: dict[Severidade, NivelResposta] = {
    Severidade.OK: NivelResposta(
        0,
        None,
        "Situação não compromete a segurança da barragem.",
        ("Manter a rotina de inspeção e monitoramento.",),
    ),
    Severidade.AVISO: NivelResposta(
        1,
        "verde",
        "Situação não compromete a segurança no curto prazo, mas deve ser controlada e monitorada.",
        (
            "Intensificar a frequência de leituras dos instrumentos envolvidos.",
            "Registrar a ocorrência e comunicar o responsável técnico.",
        ),
    ),
    Severidade.ALERTA: NivelResposta(
        2,
        "amarelo",
        "Situação representa ameaça à segurança no curto prazo; devem ser tomadas providências para eliminar o problema.",
        (
            "Acionar o coordenador do PAE e a equipe técnica.",
            "Executar as medidas corretivas previstas e inspeção especial.",
            "Notificar o órgão fiscalizador e preparar a comunicação à Defesa Civil.",
        ),
    ),
    Severidade.CRITICO: NivelResposta(
        3,
        "vermelho",
        "Alta probabilidade de ruptura ou ruptura em curso; providências para prevenção e redução de danos.",
        (
            "Declarar emergência e executar o fluxograma de notificação do PAE.",
            "Acionar sirenes e alertar a população da ZAS; comunicar a Defesa Civil imediatamente.",
            "Mobilizar recursos para mitigação e apoiar a evacuação pelas rotas de fuga.",
        ),
    ),
}


def nivel_de_resposta(severidade: Severidade) -> NivelResposta:
    return NIVEIS_RESPOSTA[severidade]
