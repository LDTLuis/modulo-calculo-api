"""Contrato JSON entre o Desktop (Java/ProcessBuilder) e o motor. Especificação: docs/contrato.md.

Requisição: {"versao_contrato", "operacao", "barragem", "configuracao", "opcoes", ...dados}
Resposta:   {"versao_contrato", "operacao", "status", "versao_config", "resultados",
             "alertas", "rejeicoes", "graficos", "erros", ...campos da operação}
"""

from __future__ import annotations

from collections.abc import Callable, Mapping

from damiq_calc import __version__, catalogo
from damiq_calc.core.resultado import severidade_maxima
from damiq_calc.medicoes import Lacuna, Medicao, detectar_lacunas, validar_lote
from damiq_calc.monitoramento import avaliar

from .configuracao import Configuracao, ler_configuracao
from .leitura import ErroContrato, datetime_com_fuso, objeto

__all__ = ["OPERACOES", "VERSAO_CONTRATO", "ErroContrato", "processar", "resposta_erro"]

VERSAO_CONTRATO = "1.0"


def resposta_base(operacao: str | None, config: Configuracao | None = None) -> dict:
    return {
        "versao_contrato": VERSAO_CONTRATO,
        "operacao": operacao,
        "status": "OK",
        "versao_config": config.versao if config else None,
        "resultados": [],
        "alertas": [],
        "rejeicoes": [],
        "graficos": [],
        "erros": [],
    }


def resposta_erro(
    operacao: str | None, codigo: str, mensagem: str, por_campo: list[dict] | None = None
) -> dict:
    """Resposta de erro. `por_campo` (entradas de cálculo) vira um erro por campo, para a tela
    marcar cada um; os demais erros têm `campo: null`."""
    resposta = resposta_base(operacao)
    resposta["status"] = "ERRO"
    if por_campo:
        resposta["erros"] = [
            {"codigo": e["codigo"], "mensagem": e["mensagem"], "campo": e["campo"]} for e in por_campo
        ]
    else:
        resposta["erros"].append({"codigo": codigo, "mensagem": mensagem, "campo": None})
    return resposta


def processar(requisicao: object) -> dict:
    if not isinstance(requisicao, Mapping):
        raise ErroContrato("A requisição deve ser um objeto JSON")
    _verificar_versao(requisicao.get("versao_contrato"))
    operacao = requisicao.get("operacao")
    manipulador = OPERACOES.get(operacao)  # type: ignore[arg-type]
    if manipulador is None:
        raise ErroContrato(
            f"Operação desconhecida: {operacao!r} (disponíveis: {', '.join(OPERACOES)})",
            codigo="OPERACAO_DESCONHECIDA",
        )
    return manipulador(requisicao)


def _verificar_versao(versao: object) -> None:
    if not isinstance(versao, str):
        raise ErroContrato("Campo 'versao_contrato' é obrigatório", codigo="VERSAO_INCOMPATIVEL")
    if versao.split(".")[0] != VERSAO_CONTRATO.split(".")[0]:
        raise ErroContrato(
            f"Versão de contrato {versao!r} incompatível com {VERSAO_CONTRATO}",
            codigo="VERSAO_INCOMPATIVEL",
        )


# --- operações -------------------------------------------------------------------------


def _op_info(requisicao: Mapping) -> dict:
    """Handshake do Desktop: versão do motor e operações suportadas."""
    resposta = resposta_base("info")
    resposta["motor"] = {"versao": __version__, "operacoes": list(OPERACOES)}
    return resposta


def _op_processar_lote(requisicao: Mapping) -> dict:
    """M1 (validação, lacunas) + M2 (alertas) sobre `medicoes`.

    `historico` (opcional, mesmo formato) são leituras anteriores já processadas, enviadas
    só como contexto para taxa de variação, janela estatística, sensor travado e lacunas.
    """
    config = ler_configuracao(requisicao)
    opcoes = objeto(requisicao.get("opcoes", {}), "opcoes")
    registros = requisicao.get("medicoes")
    if not isinstance(registros, list):
        raise ErroContrato("Campo 'medicoes' deve ser uma lista")
    registros_historico = requisicao.get("historico", [])
    if not isinstance(registros_historico, list):
        raise ErroContrato("Campo 'historico' deve ser uma lista")

    parametros = {
        "sensores": config.sensores,
        "faixas_por_tipo": config.faixas_por_tipo,
        "fuso_padrao": config.fuso_padrao,
        "tolerancia_futuro": config.tolerancia_futuro,
        "agora": datetime_com_fuso(opcoes["agora"], "opcoes.agora") if "agora" in opcoes else None,
    }
    validacao = validar_lote(registros, **parametros)
    historico = validar_lote(registros_historico, **parametros)

    lacunas = _lacunas_do_lote(validacao.medicoes, historico.medicoes, config)
    monitoramento = avaliar(validacao.medicoes, config.monitoramento, historico.medicoes)

    resposta = resposta_base("processar_lote", config)
    resposta["resumo"] = {
        "recebidas": len(registros),
        "validas": len(validacao.medicoes),
        "rejeitadas": len(validacao.rejeicoes),
        "lacunas": len(lacunas),
        "alertas": len(monitoramento.alertas),
        "historico": {
            "recebidas": len(registros_historico),
            "validas": len(historico.medicoes),
            "rejeitadas": len(historico.rejeicoes),
        },
    }
    resposta["monitoramento"] = {
        "status_barragem": monitoramento.status_barragem.name,
        "status_dados": monitoramento.status_dados.name,
        "sensores": {s: sit.para_dict() for s, sit in monitoramento.sensores.items()},
    }
    resposta["alertas"] = [a.para_dict() for a in monitoramento.alertas]
    resposta["medicoes"] = [m.para_dict() for m in validacao.medicoes]
    resposta["rejeicoes"] = [r.para_dict() for r in validacao.rejeicoes]
    resposta["rejeicoes_historico"] = [r.para_dict() for r in historico.rejeicoes]
    resposta["lacunas"] = [lac.para_dict() for lac in lacunas]
    return resposta


def _lacunas_do_lote(
    lote: list[Medicao], historico: list[Medicao], config: Configuracao
) -> list[Lacuna]:
    """Lacunas que terminam numa leitura do lote (inclui a transição histórico → lote)."""
    chaves_lote = {(m.sensor, m.timestamp) for m in lote}
    serie = lote + [m for m in historico if (m.sensor, m.timestamp) not in chaves_lote]
    frequencias = {}
    for m in serie:
        if m.sensor not in frequencias:
            frequencias[m.sensor] = config.frequencia_do_sensor(m.sensor, m.tipo)
    lacunas = detectar_lacunas(
        serie,
        {s: f for s, f in frequencias.items() if f},
        fator_tolerancia=config.fator_tolerancia_lacuna,
    )
    return [lac for lac in lacunas if (lac.sensor, lac.fim) in chaves_lote]


def _op_listar_calculos(requisicao: Mapping) -> dict:
    """Descoberta: cálculos disponíveis e os campos que cada tela deve coletar."""
    modulo = requisicao.get("modulo")
    resposta = resposta_base("listar_calculos")
    resposta["calculos"] = [
        d.para_dict() for d in catalogo.REGISTRO.values() if modulo is None or d.modulo == modulo
    ]
    return resposta


def _op_calcular(requisicao: Mapping) -> dict:
    """Executa um cálculo com os valores digitados na tela (M3–M8)."""
    calculo_id = requisicao.get("calculo")
    if not isinstance(calculo_id, str):
        raise ErroContrato("Campo 'calculo' é obrigatório (ex.: 'hidrostatica.empuxo')")
    entradas = objeto(requisicao.get("entradas", {}), "entradas")
    config = ler_configuracao(requisicao)
    execucao = catalogo.executar(calculo_id, entradas, config.limites_calculo)

    definicao = execucao.definicao
    unidades = {e.nome: e.unidade for e in definicao.entradas}
    resposta = resposta_base("calcular", config)
    resposta["calculo"] = {"id": definicao.id, "titulo": definicao.titulo, "fonte": definicao.fonte}
    resposta["entradas"] = {
        nome: {"valor": valor, "unidade": unidades[nome]} for nome, valor in execucao.entradas.items()
    }
    resposta["resultados"] = [r.para_dict() for r in execucao.resultados]
    resposta["memoria"] = {
        "passos": [p.para_dict() for p in execucao.memoria.passos],
        "premissas": list(execucao.memoria.premissas),
        "conclusoes": list(execucao.memoria.conclusoes),
    }
    resposta["status_calculo"] = severidade_maxima(r.severidade for r in execucao.resultados).name
    return resposta


OPERACOES: dict[str, Callable[[Mapping], dict]] = {
    "info": _op_info,
    "processar_lote": _op_processar_lote,
    "listar_calculos": _op_listar_calculos,
    "calcular": _op_calcular,
}
