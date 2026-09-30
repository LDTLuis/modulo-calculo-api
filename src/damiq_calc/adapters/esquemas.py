"""JSON Schema (draft 2020-12) do contrato, gerado a partir do código.

Os schemas são a referência para o back do Desktop (DTOs Jackson) e para a Central Web
(Zod / Bean Validation). Como vêm do catálogo e dos padrões do próprio motor, não divergem
dele; o teste `test_esquemas` falha se os arquivos em docs/schemas/ ficarem desatualizados.

    python -m damiq_calc.adapters.esquemas [diretorio]   # padrão: docs/schemas

Os schemas são **estritos** (`additionalProperties: false` nas entradas): servem para a
Central e o Desktop recusarem campos errados na origem. O motor é tolerante — ignora campos
desconhecidos da configuração e os devolve em `avisos`. Nas respostas, campos novos podem
surgir em versões 1.x; consumidores devem ignorar o que não conhecem.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from damiq_calc.catalogo import REGISTRO
from damiq_calc.core import unidades
from damiq_calc.core.calculo import Entrada, EntradaTabela
from damiq_calc.graficos import FORMATOS
from damiq_calc.medicoes import UNIDADE_CANONICA, TipoMedicao
from damiq_calc.monitoramento import DirecaoTaxa, ParametrosAnomalia, ParametrosTravado
from damiq_calc.monitoramento.modelo import INTERVALO_TAXA_PADRAO

from .contrato import OPERACOES, VERSAO_CONTRATO

BASE_ID = "https://github.com/LDTLuis/modulo-calculo-api/blob/main/docs/schemas/"
DRAFT = "https://json-schema.org/draft/2020-12/schema"
SEVERIDADES = ["OK", "AVISO", "ALERTA", "CRITICO"]


def _unidades_de(unidade: str) -> list[str]:
    return unidades.unidades_da_dimensao(unidades.dimensao(unidade))


UNIDADES_MEDICAO = sorted({u for canon in UNIDADE_CANONICA.values() for u in _unidades_de(canon)})
TIPOS = [t.value for t in TipoMedicao]


def _obj(propriedades: dict, obrigatorios: list[str] | None = None, **extra) -> dict:
    esquema = {"type": "object", "properties": propriedades, "additionalProperties": False, **extra}
    if obrigatorios:
        esquema["required"] = obrigatorios
    return esquema


# --- configuração ------------------------------------------------------------------------


def esquema_configuracao() -> dict:
    anomalia, travado = ParametrosAnomalia(), ParametrosTravado()
    num_ou_nulo = {"type": ["number", "null"]}
    faixa = _obj(
        {"min": num_ou_nulo, "max": num_ou_nulo, "unidade": {"enum": UNIDADES_MEDICAO}},
        description="Faixa plausível do instrumento; min ≤ max; unidade compatível com o tipo (padrão: canônica).",
        anyOf=[{"required": ["min"]}, {"required": ["max"]}],
    )
    niveis = _obj(
        {n: num_ou_nulo for n in ("aviso", "alerta", "critico")},
        description="Ao menos um nível; acima: aviso ≤ alerta ≤ critico; abaixo: aviso ≥ alerta ≥ critico.",
        minProperties=1,
    )
    positivo = {"type": "number", "exclusiveMinimum": 0}
    sensor = _obj(
        {
            "tipo": {"enum": TIPOS},
            "faixa": {"$ref": "#/$defs/faixa"},
            "frequencia_esperada_s": positivo,
            "limites_alerta": _obj(
                {"unidade": {"enum": UNIDADES_MEDICAO}, "acima": {"$ref": "#/$defs/niveis"}, "abaixo": {"$ref": "#/$defs/niveis"}},
                anyOf=[{"required": ["acima"]}, {"required": ["abaixo"]}],
            ),
            "taxa_variacao": _obj(
                {
                    "unidade": {"enum": UNIDADES_MEDICAO},
                    "intervalo_s": {**positivo, "default": INTERVALO_TAXA_PADRAO.total_seconds()},
                    "direcao": {"enum": [d.value for d in DirecaoTaxa], "default": DirecaoTaxa.AMBAS.value},
                    **{n: positivo for n in ("aviso", "alerta", "critico")},
                },
                description="Magnitudes positivas e crescentes; ao menos um nível.",
                anyOf=[{"required": [n]} for n in ("aviso", "alerta", "critico")],
            ),
            "cota_instalacao_m": {"type": "number", "description": "Reservado (M3); aceito e ainda não usado."},
        },
        ["tipo"],
    )
    limites = {}
    for definicao in REGISTRO.values():
        for lim in definicao.limites:
            limites.setdefault(
                lim.nome,
                {"type": "number", "exclusiveMinimum": 0, "default": lim.padrao, "description": lim.descricao, "x-calculos": []},
            )["x-calculos"].append(definicao.id)
    return {
        "$schema": DRAFT,
        "$id": BASE_ID + "configuracao.schema.json",
        "title": f"Configuração publicada pela Central (contrato {VERSAO_CONTRATO})",
        "type": "object",
        "required": ["versao"],
        "additionalProperties": False,
        "properties": {
            "versao": {"type": ["string", "integer"], "minLength": 1, "description": "Revisão da configuração; devolvida em versao_config."},
            "fuso_padrao": {"type": "string", "pattern": r"^[+-]\d{2}:\d{2}$", "default": "-03:00"},
            "medicoes": _obj(
                {
                    "tolerancia_futuro_s": {"type": "number", "minimum": 0, "default": 300},
                    "fator_tolerancia_lacuna": {"type": "number", "minimum": 1, "default": 1.5},
                }
            ),
            "padroes_por_tipo": {
                "type": "object",
                "propertyNames": {"enum": TIPOS},
                "additionalProperties": _obj({"faixa": {"$ref": "#/$defs/faixa"}, "frequencia_esperada_s": positivo}),
            },
            "sensores": {"type": "object", "additionalProperties": {"$ref": "#/$defs/sensor"}},
            "monitoramento": _obj(
                {
                    "anomalia": _obj(
                        {
                            "ativo": {"type": "boolean", "default": anomalia.ativo},
                            "janela_leituras": {"type": "integer", "minimum": 3, "default": anomalia.janela_leituras},
                            "minimo_leituras": {"type": "integer", "minimum": 3, "default": anomalia.minimo_leituras, "description": "≤ janela_leituras"},
                            "limiar_z": {**positivo, "default": anomalia.limiar_z},
                        }
                    ),
                    "sensor_travado": _obj(
                        {
                            "ativo": {"type": "boolean", "default": travado.ativo},
                            "leituras_consecutivas": {"type": "integer", "minimum": 2, "default": travado.leituras_consecutivas},
                        }
                    ),
                }
            ),
            "limites_calculo": _obj(dict(sorted(limites.items())), description="Critérios de aceitação dos cálculos (M4+)."),
            "barragem_parametros": {"description": "Reservado (M3–M7); aceito e ainda não usado."},
            "classificacao": {"description": "Reservado (M8); aceito e ainda não usado."},
        },
        "$defs": {"faixa": faixa, "niveis": niveis, "sensor": sensor},
    }


# --- entradas dos cálculos -----------------------------------------------------------------


def _esquema_entrada(entrada: Entrada) -> dict:
    tipo = "integer" if entrada.inteiro else "number"
    numero: dict = {"type": tipo}
    for chave, valor in (("minimum", entrada.minimo), ("maximum", entrada.maximo)):
        if valor is None:
            continue
        inclusivo = entrada.minimo_inclusivo if chave == "minimum" else entrada.maximo_inclusivo
        numero[chave if inclusivo else "exclusive" + chave.capitalize()] = valor
    variantes = [numero]
    if not entrada.inteiro:
        variantes.append(
            _obj(
                {"valor": {"type": "number"}, "unidade": {"enum": _unidades_de(entrada.unidade)}},
                ["valor"],
                description="Valor em outra unidade; os limites valem após a conversão para a unidade padrão.",
            )
        )
    esquema = {"description": f"{entrada.descricao} [{entrada.unidade}]", "anyOf": variantes}
    if entrada.padrao is not None:
        esquema["default"] = entrada.padrao
    return esquema


def esquema_entradas(definicao) -> dict:
    propriedades, obrigatorias = {}, []
    for entrada in definicao.entradas:
        if isinstance(entrada, EntradaTabela):
            colunas = {c.nome: _esquema_entrada(c) for c in entrada.colunas}
            propriedades[entrada.nome] = {
                "description": entrada.descricao,
                "type": "array",
                "minItems": entrada.min_linhas,
                "items": _obj(colunas, [c.nome for c in entrada.colunas if c.obrigatoria]),
            }
        else:
            propriedades[entrada.nome] = _esquema_entrada(entrada)
        if entrada.obrigatoria:
            obrigatorias.append(entrada.nome)
    return _obj(propriedades, obrigatorias, title=definicao.titulo, description=definicao.fonte)


def esquema_calculos() -> dict:
    return {
        "$schema": DRAFT,
        "$id": BASE_ID + "calculos.schema.json",
        "title": f"Entradas de cada cálculo da operação `calcular` (contrato {VERSAO_CONTRATO})",
        "$defs": {id_: esquema_entradas(d) for id_, d in sorted(REGISTRO.items())},
    }


# --- requisição --------------------------------------------------------------------------


def esquema_requisicao() -> dict:
    medicao = _obj(
        {
            "sensor": {"type": ["string", "integer"]},
            "tipo": {"type": "string", "description": f"Um de {TIPOS} (aceita acento e maiúsculas)."},
            "timestamp": {"type": "string", "description": "ISO 8601; sem offset, vale configuracao.fuso_padrao."},
            "valor": {"type": ["number", "string"], "description": "Número; texto aceita vírgula decimal (\"12,5\")."},
            "unidade": {"type": "string"},
        },
        ["sensor", "tipo", "timestamp", "valor", "unidade"],
        description="Registros inválidos não reprovam a requisição: voltam em `rejeicoes`.",
    )
    ids = sorted(REGISTRO)
    se_calculo = [
        {"if": {"properties": {"calculo": {"const": id_}}, "required": ["calculo"]},
         "then": {"properties": {"entradas": {"$ref": f"calculos.schema.json#/$defs/{id_}"}}}}
        for id_ in ids
    ]
    por_operacao = {
        "info": [],
        "listar_calculos": [],
        "validar_configuracao": ["configuracao"],
        "processar_lote": ["medicoes"],
        "calcular": ["calculo"],
    }
    assert set(por_operacao) == set(OPERACOES), "atualize esquema_requisicao ao criar operações"
    return {
        "$schema": DRAFT,
        "$id": BASE_ID + "requisicao.schema.json",
        "title": f"Requisição ao motor de cálculo (contrato {VERSAO_CONTRATO})",
        "type": "object",
        "required": ["versao_contrato", "operacao"],
        "additionalProperties": False,
        "properties": {
            "versao_contrato": {"type": "string", "pattern": r"^1\.\d+$", "examples": [VERSAO_CONTRATO]},
            "operacao": {"enum": list(OPERACOES)},
            "barragem": {"type": "object", "description": "Identificação da barragem (livre)."},
            "configuracao": {"$ref": "configuracao.schema.json"},
            "opcoes": _obj(
                {
                    "agora": {"type": "string", "description": "ISO 8601 com fuso."},
                    "graficos": _obj({"diretorio": {"type": "string", "minLength": 1}, "formato": {"enum": list(FORMATOS), "default": "png"}}, ["diretorio"]),
                }
            ),
            "medicoes": {"type": "array", "items": {"$ref": "#/$defs/medicao"}},
            "historico": {"type": "array", "items": {"$ref": "#/$defs/medicao"}},
            "calculo": {"enum": ids},
            "entradas": {"type": "object"},
            "modulo": {"enum": sorted({d.modulo for d in REGISTRO.values()})},
        },
        "allOf": [
            *({"if": {"properties": {"operacao": {"const": op}}}, "then": {"required": obrig}} for op, obrig in por_operacao.items() if obrig),
            *se_calculo,
        ],
        "$defs": {"medicao": medicao},
    }


# --- resposta ----------------------------------------------------------------------------


def esquema_resposta() -> dict:
    texto_ou_nulo = {"type": ["string", "null"]}
    num_ou_nulo = {"type": ["number", "null"]}
    return {
        "$schema": DRAFT,
        "$id": BASE_ID + "resposta.schema.json",
        "title": f"Resposta do motor de cálculo (contrato {VERSAO_CONTRATO})",
        "description": "Campos novos podem surgir em versões 1.x: consumidores devem ignorar o que não conhecem.",
        "type": "object",
        "required": ["versao_contrato", "operacao", "status", "versao_config", "avisos", "resultados", "alertas", "rejeicoes", "graficos", "erros"],
        "properties": {
            "versao_contrato": {"type": "string"},
            "operacao": texto_ou_nulo,
            "status": {"enum": ["OK", "ERRO"]},
            "versao_config": {"type": ["string", "integer", "null"]},
            "avisos": {"type": "array", "items": {"$ref": "#/$defs/aviso"}},
            "erros": {"type": "array", "items": {"$ref": "#/$defs/erro"}},
            "resultados": {"type": "array", "items": {"$ref": "#/$defs/resultado"}},
            "alertas": {"type": "array", "items": {"$ref": "#/$defs/alerta"}},
            "rejeicoes": {"type": "array", "items": {"$ref": "#/$defs/rejeicao"}},
            "rejeicoes_historico": {"type": "array", "items": {"$ref": "#/$defs/rejeicao"}},
            "graficos": {"type": "array", "items": {"type": "object", "required": ["tipo", "arquivo"], "properties": {"tipo": {"type": "string"}, "sensor": {"type": "string"}, "arquivo": {"type": "string"}}}},
            "status_calculo": {"enum": SEVERIDADES},
            "memoria": {
                "type": "object",
                "required": ["passos", "premissas", "conclusoes", "tabelas"],
                "properties": {
                    "passos": {"type": "array", "items": {"type": "object", "required": ["descricao", "formula", "substituicao", "valor", "unidade"], "properties": {"descricao": {"type": "string"}, "formula": {"type": "string"}, "substituicao": {"type": "string"}, "valor": {"type": "number"}, "unidade": {"type": "string"}}}},
                    "premissas": {"type": "array", "items": {"type": "string"}},
                    "conclusoes": {"type": "array", "items": {"type": "string"}},
                    "tabelas": {"type": "array", "items": {"type": "object", "required": ["titulo", "colunas", "linhas"]}},
                },
            },
            "monitoramento": {
                "type": "object",
                "required": ["status_barragem", "status_dados", "nivel_resposta", "sensores"],
                "properties": {
                    "status_barragem": {"enum": SEVERIDADES},
                    "status_dados": {"enum": SEVERIDADES},
                    "nivel_resposta": {"type": "object", "required": ["nivel", "cor", "rotulo", "situacao", "acoes"], "properties": {"nivel": {"type": "integer", "minimum": 0, "maximum": 3}, "cor": texto_ou_nulo, "rotulo": {"type": "string"}, "situacao": {"type": "string"}, "acoes": {"type": "array", "items": {"type": "string"}}}},
                    "sensores": {"type": "object", "additionalProperties": {"type": "object", "required": ["tipo", "ultima_leitura", "status_atual", "status_maximo"], "properties": {"status_atual": {"enum": SEVERIDADES}, "status_maximo": {"enum": SEVERIDADES}}}},
                },
            },
        },
        "$defs": {
            "aviso": {"type": "object", "required": ["codigo", "campo", "mensagem"], "properties": {"codigo": {"type": "string"}, "campo": {"type": "string"}, "mensagem": {"type": "string"}}},
            "erro": {"type": "object", "required": ["codigo", "mensagem", "campo"], "properties": {"codigo": {"type": "string"}, "mensagem": {"type": "string"}, "campo": texto_ou_nulo}},
            "resultado": {
                "type": "object",
                "required": ["calculo", "descricao", "valor", "unidade", "status", "limite", "premissas", "fonte", "rotulo"],
                "properties": {"calculo": {"type": "string"}, "descricao": texto_ou_nulo, "valor": {"type": "number"}, "unidade": {"type": "string"}, "status": {"enum": SEVERIDADES}, "limite": num_ou_nulo, "premissas": {"type": "array", "items": {"type": "string"}}, "fonte": texto_ou_nulo, "rotulo": texto_ou_nulo},
            },
            "alerta": {
                "type": "object",
                "required": ["tipo", "categoria", "sensor", "severidade", "inicio", "fim", "leituras", "valor_extremo", "unidade", "limite", "direcao", "leitura_suspeita", "mensagem", "detalhe"],
                "properties": {"tipo": {"enum": ["LIMITE", "TAXA_VARIACAO", "FORA_FAIXA_PLAUSIVEL", "SENSOR_TRAVADO", "ANOMALIA_ESTATISTICA"]}, "categoria": {"enum": ["SEGURANCA", "QUALIDADE"]}, "severidade": {"enum": SEVERIDADES}, "leituras": {"type": "integer", "minimum": 1}, "leitura_suspeita": {"type": "boolean"}},
            },
            "rejeicao": {"type": "object", "required": ["indice", "codigo", "mensagem"], "properties": {"indice": {"type": "integer", "minimum": 0}, "codigo": {"type": "string"}, "mensagem": {"type": "string"}}},
        },
    }


ESQUEMAS = {
    "configuracao.schema.json": esquema_configuracao,
    "calculos.schema.json": esquema_calculos,
    "requisicao.schema.json": esquema_requisicao,
    "resposta.schema.json": esquema_resposta,
}


def serializar(esquema: dict) -> str:
    return json.dumps(esquema, ensure_ascii=False, indent=2) + "\n"


def gerar(diretorio: Path) -> list[Path]:
    diretorio.mkdir(parents=True, exist_ok=True)
    caminhos = []
    for nome, construir in ESQUEMAS.items():
        caminho = diretorio / nome
        caminho.write_text(serializar(construir()), encoding="utf-8", newline="\n")
        caminhos.append(caminho)
    return caminhos


if __name__ == "__main__":
    destino = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("docs/schemas")
    for c in gerar(destino):
        print(c)
