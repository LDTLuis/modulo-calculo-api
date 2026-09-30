"""Gera docs/central/guia-configuracao.md a partir de docs/schemas/configuracao.schema.json.

    python scripts/gerar_guia_central.py

O exemplo do guia é validado contra o schema e executado no motor (validar_configuracao),
e a resposta mostrada é a resposta real — o guia não diverge do código.
"""

from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator

import damiq_calc
from damiq_calc.adapters.contrato import VERSAO_CONTRATO, processar
from damiq_calc.core import unidades
from damiq_calc.medicoes import UNIDADE_CANONICA

RAIZ = Path(__file__).resolve().parents[1]
ESQUEMA = json.loads((RAIZ / "docs/schemas/configuracao.schema.json").read_text(encoding="utf-8"))
SAIDA = RAIZ / "docs/central/guia-configuracao.md"

TIPOS_JSON = {"string": "texto", "integer": "inteiro", "number": "número", "boolean": "booleano", "null": "null", "object": "objeto", "array": "lista"}
REFS = {"#/$defs/faixa": ("faixa", "3.5"), "#/$defs/niveis": ("níveis", "3.7"), "#/$defs/sensor": ("sensor", "3.4")}

EXEMPLO = {
    "versao": 12,
    "fuso_padrao": "-03:00",
    "medicoes": {"tolerancia_futuro_s": 300, "fator_tolerancia_lacuna": 1.5},
    "padroes_por_tipo": {
        "pressao": {"faixa": {"min": 0, "max": 10, "unidade": "bar"}, "frequencia_esperada_s": 604800},
        "vazao": {"faixa": {"min": 0, "unidade": "L/s"}},
    },
    "sensores": {
        "PZ-01": {
            "tipo": "pressao",
            "faixa": {"min": 0, "max": 500, "unidade": "kPa"},
            "frequencia_esperada_s": 604800,
            "limites_alerta": {"unidade": "mca", "acima": {"aviso": 18, "alerta": 22, "critico": 26}},
        },
        "RN-01": {
            "tipo": "nivel",
            "limites_alerta": {"acima": {"critico": 749.5}, "abaixo": {"aviso": 745.0, "critico": 744.0}},
            "taxa_variacao": {"unidade": "cm", "intervalo_s": 86400, "direcao": "descida", "aviso": 20, "alerta": 50},
        },
    },
    "monitoramento": {
        "anomalia": {"ativo": True, "janela_leituras": 24, "minimo_leituras": 8, "limiar_z": 3.5},
        "sensor_travado": {"ativo": False},
    },
    "limites_calculo": {"fs_min_piping": 1.5, "fs_min_talude": 1.5, "borda_livre_min": 1.0},
}


# --- formatação ---------------------------------------------------------------------------


def _valor(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return f"`{json.dumps(v, ensure_ascii=False)}`"


def _tipo(no: dict) -> str:
    if "$ref" in no:
        nome, secao = REFS[no["$ref"]]
        return f"objeto *{nome}* (§{secao})"
    if "enum" in no:
        return "texto: " + " · ".join(f"`{x}`" for x in no["enum"])
    tipos = no.get("type")
    if tipos is None:
        return "—"
    tipos = tipos if isinstance(tipos, list) else [tipos]
    texto = " ou ".join(TIPOS_JSON[t] for t in tipos)
    if tipos == ["object"] and isinstance(no.get("additionalProperties"), dict) and "properties" not in no:
        texto = "mapa (chave → objeto)"
    return texto


def _regras(no: dict) -> str:
    regras = []
    for chave, simbolo in (("minimum", "≥"), ("exclusiveMinimum", ">"), ("maximum", "≤"), ("exclusiveMaximum", "<")):
        if chave in no:
            regras.append(f"{simbolo} {_valor(no[chave])[1:-1]}")
    if "pattern" in no:
        regras.append(f"formato `{no['pattern']}`")
    if "minLength" in no:
        regras.append("não vazio")
    if "propertyNames" in no:
        regras.append("chaves: " + " · ".join(f"`{x}`" for x in no["propertyNames"]["enum"]))
    if "anyOf" in no:
        grupos = [" ou ".join(f"`{c}`" for c in g["required"]) for g in no["anyOf"]]
        regras.append("informe ao menos um: " + ", ".join(grupos))
    if no.get("minProperties"):
        regras.append(f"ao menos {no['minProperties']} campo")
    return "; ".join(regras) or "—"


def tabela_campos(no: dict, prefixo: str = "") -> list[str]:
    obrigatorios = set(no.get("required", []))
    linhas = ["| Campo | Tipo | Obrigatório | Padrão | Regras | Descrição |", "|---|---|---|---|---|---|"]
    for nome, filho in no["properties"].items():
        descricao = filho.get("description", "").replace("|", "\\|")
        tipo = "texto: unidade compatível com o tipo do sensor (§4)" if nome == "unidade" else _tipo(filho)
        linhas.append(
            f"| `{prefixo}{nome}` | {tipo} | {'**sim**' if nome in obrigatorios else 'não'} | "
            f"{_valor(filho['default']) if 'default' in filho else '—'} | {_regras(filho)} | {descricao} |"
        )
    return linhas


# --- documento ----------------------------------------------------------------------------


def gerar() -> str:
    props = ESQUEMA["properties"]
    defs = ESQUEMA["$defs"]
    sensor = defs["sensor"]["properties"]
    monit = props["monitoramento"]["properties"]

    validador = Draft202012Validator(ESQUEMA)
    erros_exemplo = [e.message for e in validador.iter_errors(EXEMPLO)]
    assert not erros_exemplo, erros_exemplo
    resposta = processar({"versao_contrato": VERSAO_CONTRATO, "operacao": "validar_configuracao", "configuracao": EXEMPLO})
    assert resposta["status"] == "OK" and not resposta["avisos"], resposta
    invalida = dict(EXEMPLO, sensores={"PZ-01": {"tipo": "pressao", "faixa": {"min": 5, "max": 1}}})
    try:
        processar({"versao_contrato": VERSAO_CONTRATO, "operacao": "validar_configuracao", "configuracao": invalida})
        raise AssertionError("o exemplo inválido deveria falhar")
    except Exception as erro:  # noqa: BLE001
        erro_invalido = {"codigo": erro.codigo, "campo": erro.campo, "mensagem": erro.mensagem}
    resumo = {k: resposta[k] for k in ("status", "versao_config", "avisos", "configuracao")}

    unidades_linhas = ["| Tipo | Unidade canônica | Unidades aceitas |", "|---|---|---|"]
    for tipo, canon in UNIDADE_CANONICA.items():
        aceitas = " · ".join(f"`{u}`" for u in unidades.unidades_da_dimensao(unidades.dimensao(canon)))
        unidades_linhas.append(f"| `{tipo.value}` | `{canon}` | {aceitas} |")

    limites_linhas = ["| Limite | Padrão | Descrição | Usado em |", "|---|---|---|---|"]
    for nome, lim in props["limites_calculo"]["properties"].items():
        usos = "<br>".join(f"`{c}`" for c in lim["x-calculos"])
        limites_linhas.append(f"| `{nome}` | {_valor(lim['default'])} | {lim['description']} | {usos} |")

    j = lambda obj: json.dumps(obj, ensure_ascii=False, indent=2)  # noqa: E731
    partes = [
        "# Guia da Configuração — Central de Configurações Web",
        "",
        f"Motor de cálculo DAMIQ **{damiq_calc.__version__}** · contrato JSON **{VERSAO_CONTRATO}** · "
        "gerado a partir de `docs/schemas/configuracao.schema.json` (`python scripts/gerar_guia_central.py`).",
        "",
        "## 1. Visão geral",
        "",
        "A Central é a **dona dos parâmetros** de monitoramento e dos critérios dos cálculos. Ela publica a configuração, o Desktop guarda a última versão válida (SQLite) e a envia ao motor em toda chamada. O motor não guarda estado e devolve `versao_config` em cada resposta, para que o log registre qual versão gerou cada resultado (RF-12).",
        "",
        "```",
        "Central Web ──REST/JSON──▶ Desktop ──validar_configuracao──▶ motor",
        "  (cadastra, versiona)      (grava no SQLite se válida)       (valida, aplica)",
        "```",
        "",
        "| Quem cadastra | O quê |",
        "|---|---|",
        "| Técnico | Tipo, faixa plausível (ficha do instrumento) e frequência de leitura de cada sensor |",
        "| Engenheiro | Limites de alerta, taxa de variação e critérios dos cálculos (`limites_calculo`) |",
        "| Administrador | Parâmetros gerais (fuso, tolerâncias, detecção de anomalia e de sensor travado) |",
        "",
        "> **Faixa plausível ≠ limite de alerta.** A faixa descreve o que o **instrumento** mede: fora dela, a leitura é mantida e marcada como suspeita (qualidade de dados). Os limites de alerta descrevem a **segurança da barragem** e geram alertas de Aviso/Alerta/Crítico. Não misture os dois num mesmo campo da tela.",
        "",
        "## 2. Estrutura",
        "",
        "```",
        "configuracao",
        "├── versao                      (obrigatório)",
        "├── fuso_padrao",
        "├── medicoes                    tolerâncias gerais",
        "├── padroes_por_tipo",
        "│   └── <tipo>                  faixa, frequencia_esperada_s",
        "├── sensores",
        "│   └── <id do sensor>          tipo, faixa, frequencia_esperada_s, limites_alerta, taxa_variacao",
        "├── monitoramento              anomalia, sensor_travado",
        "└── limites_calculo            critérios dos cálculos (FS mínimos etc.)",
        "```",
        "",
        "**Prioridade:** o valor do sensor vale primeiro; se não houver, vale o de `padroes_por_tipo`; por último, o padrão do motor.",
        "",
        "## 3. Campos",
        "",
        "### 3.1 Raiz",
        "",
        *tabela_campos(ESQUEMA),
        "",
        "### 3.2 `medicoes`",
        "",
        *tabela_campos(props["medicoes"]),
        "",
        "### 3.3 `padroes_por_tipo.<tipo>`",
        "",
        *tabela_campos(props["padroes_por_tipo"]["additionalProperties"]),
        "",
        "### 3.4 `sensores.<id>` — sensor",
        "",
        *tabela_campos(defs["sensor"]),
        "",
        "### 3.5 Faixa plausível — `faixa`",
        "",
        *tabela_campos(defs["faixa"]),
        "",
        f"Regras: {_regras(defs['faixa'])}; **min ≤ max**.",
        "",
        "### 3.6 `limites_alerta`",
        "",
        *tabela_campos(sensor["limites_alerta"]),
        "",
        f"Regras: {_regras(sensor['limites_alerta'])}. Os dois lados podem coexistir (ex.: NA com limite máximo e mínimo).",
        "",
        "### 3.7 Níveis — `acima` / `abaixo`",
        "",
        *tabela_campos(defs["niveis"]),
        "",
        "Regras: ao menos um nível; em `acima`, **aviso ≤ alerta ≤ critico**; em `abaixo`, **aviso ≥ alerta ≥ critico**. Um nível omitido não é avaliado.",
        "",
        "### 3.8 `taxa_variacao`",
        "",
        *tabela_campos(sensor["taxa_variacao"]),
        "",
        f"Regras: {_regras(sensor['taxa_variacao'])}; níveis positivos e **crescentes**. A taxa é calculada entre leituras consecutivas e extrapolada para `intervalo_s` (0,3 m em 2 dias = 0,15 m/dia).",
        "",
        "### 3.9 `monitoramento.anomalia`",
        "",
        *tabela_campos(monit["anomalia"]),
        "",
        "### 3.10 `monitoramento.sensor_travado`",
        "",
        *tabela_campos(monit["sensor_travado"]),
        "",
        "## 4. Unidades aceitas",
        "",
        "Toda faixa, limite e taxa aceita `unidade`. O motor converte para a unidade canônica do tipo do sensor. Uma unidade de outra dimensão (ex.: `kPa` num sensor de nível) é recusada.",
        "",
        *unidades_linhas,
        "",
        "> `mca` (metro de coluna d'água) é convertido com 1 mca = 9,81 kPa.",
        "",
        "## 5. Critérios dos cálculos — `limites_calculo`",
        "",
        "Critérios de aceitação usados pela operação `calcular`, definidos pelo engenheiro responsável. Um critério ausente usa o padrão do motor. A memória de cálculo registra a origem (\"padrão do motor\" ou \"configuração da Central\") para o laudo. Todos os valores são números > 0.",
        "",
        *limites_linhas,
        "",
        "## 6. Regras que o JSON Schema não expressa",
        "",
        "Estas regras envolvem mais de um campo. A tela da Central deve validá-las, e o motor as confere em `validar_configuracao`:",
        "",
        "| Regra | Onde |",
        "|---|---|",
        "| `min ≤ max` | toda `faixa` |",
        "| `acima`: aviso ≤ alerta ≤ critico · `abaixo`: aviso ≥ alerta ≥ critico | `limites_alerta` |",
        "| Níveis positivos e crescentes | `taxa_variacao` |",
        "| `minimo_leituras ≤ janela_leituras` | `monitoramento.anomalia` |",
        "| `unidade` compatível com o `tipo` do sensor (§4) | `faixa`, `limites_alerta`, `taxa_variacao` |",
        "| Em `padroes_por_tipo`, a unidade da faixa segue o tipo da chave | `padroes_por_tipo.<tipo>.faixa` |",
        "",
        "## 7. Exemplo completo",
        "",
        "Configuração válida no schema e no motor (verificada ao gerar este guia):",
        "",
        "```json",
        j(EXEMPLO),
        "```",
        "",
        "## 8. Validação antes de publicar",
        "",
        "O Desktop chama `validar_configuracao` ao receber uma nova versão e só a grava se for válida. Resposta real do motor para o exemplo acima:",
        "",
        "```json",
        j(resumo),
        "```",
        "",
        "Configuração inválida (ex.: `faixa` com min 5 e max 1): saída 1, `status: \"ERRO\"`, e o erro aponta o campo:",
        "",
        "```json",
        j({"erros": [erro_invalido]}),
        "```",
        "",
        "**Campos desconhecidos** (erro de digitação, como `limite_alerta` ou `fs_min_pipping`) não reprovam a configuração no motor. Eles são ignorados e voltam em `avisos` com o caminho do campo. O schema, por ser estrito, **recusa** esses campos: validando na Central, eles nem chegam a ser publicados.",
        "",
        "## 9. Implementação na Central",
        "",
        "- **Validação:** use o schema como referência para os schemas Zod (front-end) e o Bean Validation (Spring). Ele é estrito (`additionalProperties: false`): campos fora dele devem ser recusados na origem.",
        "- **Padrões:** os campos `default` do schema são os padrões do motor. A tela pode exibi-los como sugestão; não é preciso enviá-los.",
        "- **Versão:** incremente `versao` a cada publicação (texto ou inteiro). Ela volta em `versao_config` nas respostas do motor e permite rastrear resultados e alertas até a configuração que os gerou.",
        "- **Nomes de critérios:** a lista de `limites_calculo` (§5) vem do catálogo de cálculos. Novos critérios podem surgir em versões 1.x do motor; atualize a tela a partir do schema da versão em uso.",
        "- **Campos reservados:** `cota_instalacao_m` (sensor), `barragem_parametros` e `classificacao` são aceitos, mas ainda não têm efeito no motor 1.0.",
        "",
        '<div class="quebra"></div>',
        "",
        "## Apêndice A — `configuracao.schema.json`",
        "",
        "```json",
        j(ESQUEMA),
        "```",
        "",
    ]
    return "\n".join(partes)


if __name__ == "__main__":
    SAIDA.parent.mkdir(parents=True, exist_ok=True)
    SAIDA.write_text(gerar(), encoding="utf-8", newline="\n")
    print(SAIDA)
