# Guia da Configuração — Central de Configurações Web

Motor de cálculo DAMIQ **1.0.0** · contrato JSON **1.0** · gerado a partir de `docs/schemas/configuracao.schema.json` (`python scripts/gerar_guia_central.py`).

## 1. Visão geral

> **Terminologia:** *instrumento* é o ponto de medição instalado na barragem (piezômetro, régua de nível, medidor de vazão, marco de deslocamento). Ele é lido pelo técnico de campo, e as leituras são digitadas ou importadas: não há sensores automáticos. No JSON, os campos mantêm os nomes do contrato 1.0: `sensor` (na medição), `sensores` (na configuração) e `sensor_travado` (detecção de valor repetido).

A Central é a **dona dos parâmetros** de monitoramento e dos critérios dos cálculos. Ela publica a configuração, o Desktop guarda a última versão válida (SQLite) e a envia ao motor em toda chamada. O motor não guarda estado e devolve `versao_config` em cada resposta, para que o log registre qual versão gerou cada resultado (RF-12).

```
Central Web ──REST/JSON──▶ Desktop ──validar_configuracao──▶ motor
  (cadastra, versiona)      (grava no SQLite se válida)       (valida, aplica)
```

| Quem cadastra | O quê |
|---|---|
| Técnico | Tipo, faixa plausível (ficha do instrumento) e frequência de leitura de cada instrumento |
| Engenheiro | Limites de alerta, taxa de variação e critérios dos cálculos (`limites_calculo`) |
| Administrador | Parâmetros gerais (fuso, tolerâncias, detecção de anomalia e de instrumento travado) |

> **Faixa plausível ≠ limite de alerta.** A faixa descreve o que o **instrumento** mede: fora dela, a leitura é mantida e marcada como suspeita (qualidade de dados). Os limites de alerta descrevem a **segurança da barragem** e geram alertas de Aviso/Alerta/Crítico. Não misture os dois num mesmo campo da tela.

## 2. Estrutura

```
configuracao
├── versao                      (obrigatório)
├── fuso_padrao
├── medicoes                    tolerâncias gerais
├── padroes_por_tipo
│   └── <tipo>                  faixa, frequencia_esperada_s
├── sensores
│   └── <id do instrumento>     tipo, faixa, frequencia_esperada_s, limites_alerta, taxa_variacao
├── monitoramento               anomalia, sensor_travado
└── limites_calculo             critérios dos cálculos (FS mínimos etc.)
```

**Prioridade:** o valor do instrumento vale primeiro; se não houver, vale o de `padroes_por_tipo`; por último, o padrão do motor.

## 3. Campos

### 3.1 Raiz

| Campo | Tipo | Obrigatório | Padrão | Regras | Descrição |
|---|---|---|---|---|---|
| `versao` | texto ou inteiro | **sim** | — | não vazio | Revisão da configuração; devolvida em versao_config. |
| `fuso_padrao` | texto | não | `"-03:00"` | formato `^[+-]\d{2}:\d{2}$` | Offset aplicado a timestamps de medição sem fuso (ex.: "-03:00"). Nomes de fuso não são aceitos. |
| `medicoes` | objeto | não | — | — | Parâmetros gerais de validação das medições (M1). |
| `padroes_por_tipo` | mapa (chave → objeto) | não | — | chaves: `nivel` · `pressao` · `vazao` · `deslocamento` | Valores padrão por tipo de medição (chave: nivel, pressao, vazao ou deslocamento), usados pelos instrumentos sem valor próprio. |
| `sensores` | mapa (chave → objeto) | não | — | — | Cadastro por instrumento; a chave é o identificador do instrumento, igual ao campo `sensor` das medições. |
| `monitoramento` | objeto | não | — | — | Parâmetros gerais das regras de qualidade de dados (M2). |
| `limites_calculo` | objeto | não | — | — | Critérios de aceitação dos cálculos (M4+). |
| `barragem_parametros` | — | não | — | — | Reservado (M3–M7); aceito e ainda não usado. |
| `classificacao` | — | não | — | — | Reservado (M8); aceito e ainda não usado. |

### 3.2 `medicoes`

| Campo | Tipo | Obrigatório | Padrão | Regras | Descrição |
|---|---|---|---|---|---|
| `tolerancia_futuro_s` | número | não | `300` | ≥ 0 | Folga, em segundos, para aceitar leituras com horário à frente do relógio (coletores dessincronizados). |
| `fator_tolerancia_lacuna` | número | não | `1.5` | ≥ 1 | Há lacuna quando o intervalo entre leituras de um instrumento passa de frequência esperada × fator. |

### 3.3 `padroes_por_tipo.<tipo>`

| Campo | Tipo | Obrigatório | Padrão | Regras | Descrição |
|---|---|---|---|---|---|
| `faixa` | objeto *faixa* (§3.5) | não | — | — | Faixa plausível padrão do tipo. |
| `frequencia_esperada_s` | número | não | — | > 0 | Intervalo esperado entre leituras, em segundos (detecção de lacunas). |

### 3.4 `sensores.<id>` — instrumento

| Campo | Tipo | Obrigatório | Padrão | Regras | Descrição |
|---|---|---|---|---|---|
| `tipo` | texto: `nivel` · `pressao` · `vazao` · `deslocamento` | **sim** | — | — | Tipo cadastrado; leituras desse instrumento com outro tipo são rejeitadas (TIPO_DIVERGENTE). |
| `faixa` | objeto *faixa* (§3.5) | não | — | — | Faixa plausível do instrumento (ficha técnica). Fora dela, a leitura é mantida com a flag FORA_FAIXA_PLAUSIVEL. |
| `frequencia_esperada_s` | número | não | — | > 0 | Intervalo esperado entre leituras deste instrumento, em segundos; prevalece sobre o padrão do tipo. |
| `limites_alerta` | objeto | não | — | informe ao menos um: `acima`, `abaixo` | Limites de engenharia (RF-06), cadastrados pelo engenheiro; geram alertas de SEGURANCA. |
| `taxa_variacao` | objeto | não | — | informe ao menos um: `aviso`, `alerta`, `critico` | Velocidade máxima de variação entre leituras consecutivas (ex.: rebaixamento rápido do NA). |
| `cota_instalacao_m` | número | não | — | — | Reservado (M3); aceito e ainda não usado. |

### 3.5 Faixa plausível — `faixa`

| Campo | Tipo | Obrigatório | Padrão | Regras | Descrição |
|---|---|---|---|---|---|
| `min` | número ou null | não | — | — | Limite inferior (null = aberto). |
| `max` | número ou null | não | — | — | Limite superior (null = aberto). |
| `unidade` | texto: unidade compatível com o tipo do instrumento (§4) | não | — | — | Unidade de min/max; compatível com o tipo do instrumento. Padrão: unidade canônica do tipo. |

Regras: informe ao menos um: `min`, `max`; **min ≤ max**.

### 3.6 `limites_alerta`

| Campo | Tipo | Obrigatório | Padrão | Regras | Descrição |
|---|---|---|---|---|---|
| `unidade` | texto: unidade compatível com o tipo do instrumento (§4) | não | — | — | Unidade dos níveis; padrão: unidade canônica do tipo. |
| `acima` | objeto *níveis* (§3.7) | não | — | — | Aciona quando o valor é ≥ nível. Ordem: aviso ≤ alerta ≤ critico. |
| `abaixo` | objeto *níveis* (§3.7) | não | — | — | Aciona quando o valor é ≤ nível. Ordem: aviso ≥ alerta ≥ critico. |

Regras: informe ao menos um: `acima`, `abaixo`. Os dois lados podem coexistir (ex.: NA com limite máximo e mínimo).

### 3.7 Níveis — `acima` / `abaixo`

| Campo | Tipo | Obrigatório | Padrão | Regras | Descrição |
|---|---|---|---|---|---|
| `aviso` | número ou null | não | — | — | Valor que aciona AVISO (null ou ausente = não avaliado). |
| `alerta` | número ou null | não | — | — | Valor que aciona ALERTA (null ou ausente = não avaliado). |
| `critico` | número ou null | não | — | — | Valor que aciona CRITICO (null ou ausente = não avaliado). |

Regras: ao menos um nível; em `acima`, **aviso ≤ alerta ≤ critico**; em `abaixo`, **aviso ≥ alerta ≥ critico**. Um nível omitido não é avaliado.

### 3.8 `taxa_variacao`

| Campo | Tipo | Obrigatório | Padrão | Regras | Descrição |
|---|---|---|---|---|---|
| `unidade` | texto: unidade compatível com o tipo do instrumento (§4) | não | — | — | Unidade da variação; padrão: unidade canônica do tipo. |
| `intervalo_s` | número | não | `86400` | > 0 | Intervalo de referência da taxa, em segundos (86400 = por dia). |
| `direcao` | texto: `subida` · `descida` · `ambas` | não | `"ambas"` | — | Sentido avaliado: subida, descida ou ambas. |
| `aviso` | número | não | — | > 0 | Variação no intervalo que aciona AVISO. |
| `alerta` | número | não | — | > 0 | Variação no intervalo que aciona ALERTA. |
| `critico` | número | não | — | > 0 | Variação no intervalo que aciona CRITICO. |

Regras: informe ao menos um: `aviso`, `alerta`, `critico`; níveis positivos e **crescentes**. A taxa é calculada entre leituras consecutivas e extrapolada para `intervalo_s` (0,3 m em 2 dias = 0,15 m/dia).

### 3.9 `monitoramento.anomalia`

| Campo | Tipo | Obrigatório | Padrão | Regras | Descrição |
|---|---|---|---|---|---|
| `ativo` | booleano | não | true | — | Liga a detecção estatística. |
| `janela_leituras` | inteiro | não | `24` | ≥ 3 | Quantidade de leituras anteriores que formam a referência. |
| `minimo_leituras` | inteiro | não | `8` | ≥ 3 | Leituras anteriores mínimas para avaliar; deve ser ≤ janela_leituras. |
| `limiar_z` | número | não | `3.5` | > 0 | Aciona quando \|z\| passa deste valor (z = 0,6745·(x − mediana)/MAD). |

### 3.10 `monitoramento.sensor_travado`

| Campo | Tipo | Obrigatório | Padrão | Regras | Descrição |
|---|---|---|---|---|---|
| `ativo` | booleano | não | false | — | Liga a detecção de instrumento travado. |
| `leituras_consecutivas` | inteiro | não | `12` | ≥ 2 | Quantidade de valores idênticos seguidos para acionar. |

## 4. Unidades aceitas

Toda faixa, limite e taxa aceita `unidade`. O motor converte para a unidade canônica do tipo do instrumento. Uma unidade de outra dimensão (ex.: `kPa` num instrumento de nível) é recusada.

| Tipo | Unidade canônica | Unidades aceitas |
|---|---|---|
| `nivel` | `m` | `m` · `cm` · `mm` · `km` |
| `pressao` | `kPa` | `kPa` · `Pa` · `MPa` · `bar` · `psi` · `mca` |
| `vazao` | `m3/s` | `m3/s` · `m3/h` · `L/s` · `L/min` · `L/h` |
| `deslocamento` | `mm` | `m` · `cm` · `mm` · `km` |

> `mca` (metro de coluna d'água) é convertido com 1 mca = 9,81 kPa.

## 5. Critérios dos cálculos — `limites_calculo`

Critérios de aceitação usados pela operação `calcular`, definidos pelo engenheiro responsável. Um critério ausente usa o padrão do motor. A memória de cálculo registra a origem ("padrão do motor" ou "configuração da Central") para o laudo. Todos os valores são números > 0.

| Limite | Padrão | Descrição | Usado em |
|---|---|---|---|
| `borda_livre_min` | `1` | Borda livre mínima acima do NA máximo (m) | `geometria.borda_livre` |
| `cri_limite_alto` | `60` | CRI a partir do qual a categoria de risco é ALTA | `classificacao.risco` |
| `cri_limite_medio` | `35` | CRI acima do qual a categoria de risco é MÉDIA | `classificacao.risco` |
| `dpa_limite_alto` | `16` | DPA a partir do qual o dano potencial é ALTO | `classificacao.risco` |
| `dpa_limite_medio` | `10` | DPA acima do qual o dano potencial é MÉDIO | `classificacao.enquadramento_pnsb`<br>`classificacao.risco` |
| `ec_item_risco_alto` | `10` | Pontuação de um item de EC que torna o risco ALTO automaticamente | `classificacao.risco` |
| `fator_filtro_terzaghi` | `5` | Fator dos critérios de filtro de Terzaghi | `percolacao.filtro_terzaghi` |
| `fs_min_deslizamento` | `1.5` | Fator de segurança n contra escorregamento (P·f ≥ E·n) | `estabilidade.gravidade_deslizamento` |
| `fs_min_piping` | `1.5` | FS mínimo contra areia movediça/piping (i_crit / i_saída) | `percolacao.piping` |
| `fs_min_talude` | `1.5` | FS mínimo de estabilidade de taludes (NBR 11.682) | `estabilidade.talude_fellenius`<br>`estabilidade.talude_bishop` |
| `largura_min_crista` | `2.5` | Largura mínima da crista (m) | `geometria.secao_macico` |
| `relacao_min_agua_terra` | `3` | Relação mínima volume de água : volume de terra | `geometria.volume_terra` |
| `talude_min_jusante` | `2` | Inclinação mínima recomendada do talude de jusante (H:V) | `geometria.secao_macico` |
| `talude_min_montante` | `3` | Inclinação mínima recomendada do talude de montante (H:V) | `geometria.secao_macico` |
| `zas_distancia_max_km` | `10` | Extensão máxima da ZAS a jusante (km) | `emergencia.zas` |
| `zas_tempo_chegada_min` | `30` | Tempo de chegada da onda que delimita a ZAS (min) | `emergencia.zas` |

## 6. Regras que o JSON Schema não expressa

Estas regras envolvem mais de um campo. A tela da Central deve validá-las, e o motor as confere em `validar_configuracao`:

| Regra | Onde |
|---|---|
| `min ≤ max` | toda `faixa` |
| `acima`: aviso ≤ alerta ≤ critico · `abaixo`: aviso ≥ alerta ≥ critico | `limites_alerta` |
| Níveis positivos e crescentes | `taxa_variacao` |
| `minimo_leituras ≤ janela_leituras` | `monitoramento.anomalia` |
| `unidade` compatível com o `tipo` do instrumento (§4) | `faixa`, `limites_alerta`, `taxa_variacao` |
| Em `padroes_por_tipo`, a unidade da faixa segue o tipo da chave | `padroes_por_tipo.<tipo>.faixa` |

## 7. Exemplo completo

Configuração válida no schema e no motor (verificada ao gerar este guia):

```json
{
  "versao": 12,
  "fuso_padrao": "-03:00",
  "medicoes": {
    "tolerancia_futuro_s": 300,
    "fator_tolerancia_lacuna": 1.5
  },
  "padroes_por_tipo": {
    "pressao": {
      "faixa": {
        "min": 0,
        "max": 10,
        "unidade": "bar"
      },
      "frequencia_esperada_s": 604800
    },
    "vazao": {
      "faixa": {
        "min": 0,
        "unidade": "L/s"
      }
    }
  },
  "sensores": {
    "PZ-01": {
      "tipo": "pressao",
      "faixa": {
        "min": 0,
        "max": 500,
        "unidade": "kPa"
      },
      "frequencia_esperada_s": 604800,
      "limites_alerta": {
        "unidade": "mca",
        "acima": {
          "aviso": 18,
          "alerta": 22,
          "critico": 26
        }
      }
    },
    "RN-01": {
      "tipo": "nivel",
      "limites_alerta": {
        "acima": {
          "critico": 749.5
        },
        "abaixo": {
          "aviso": 745.0,
          "critico": 744.0
        }
      },
      "taxa_variacao": {
        "unidade": "cm",
        "intervalo_s": 86400,
        "direcao": "descida",
        "aviso": 20,
        "alerta": 50
      }
    }
  },
  "monitoramento": {
    "anomalia": {
      "ativo": true,
      "janela_leituras": 24,
      "minimo_leituras": 8,
      "limiar_z": 3.5
    },
    "sensor_travado": {
      "ativo": false
    }
  },
  "limites_calculo": {
    "fs_min_piping": 1.5,
    "fs_min_talude": 1.5,
    "borda_livre_min": 1.0
  }
}
```

## 8. Validação antes de publicar

O Desktop chama `validar_configuracao` ao receber uma nova versão e só a grava se for válida. Resposta real do motor para o exemplo acima:

```json
{
  "status": "OK",
  "versao_config": 12,
  "avisos": [],
  "configuracao": {
    "valida": true,
    "resumo": {
      "sensores": 2,
      "sensores_com_regras_de_alerta": 2,
      "padroes_por_tipo": [
        "pressao",
        "vazao"
      ],
      "limites_calculo": [
        "borda_livre_min",
        "fs_min_piping",
        "fs_min_talude"
      ],
      "anomalia_estatistica": true,
      "sensor_travado": false
    }
  }
}
```

Configuração inválida (ex.: `faixa` com min 5 e max 1): saída 1, `status: "ERRO"`, e o erro aponta o campo:

```json
{
  "erros": [
    {
      "codigo": "CONTRATO_INVALIDO",
      "campo": "configuracao.sensores.PZ-01.faixa",
      "mensagem": "'configuracao.sensores.PZ-01.faixa': min (5) maior que max (1)"
    }
  ]
}
```

**Campos desconhecidos** (erro de digitação, como `limite_alerta` ou `fs_min_pipping`) não reprovam a configuração no motor. Eles são ignorados e voltam em `avisos` com o caminho do campo. O schema, por ser estrito, **recusa** esses campos: validando na Central, eles nem chegam a ser publicados.

## 9. Implementação na Central

- **Validação:** use o schema como referência para os schemas Zod (front-end) e o Bean Validation (Spring). Ele é estrito (`additionalProperties: false`): campos fora dele devem ser recusados na origem.
- **Padrões:** os campos `default` do schema são os padrões do motor. A tela pode exibi-los como sugestão; não é preciso enviá-los.
- **Versão:** incremente `versao` a cada publicação (texto ou inteiro). Ela volta em `versao_config` nas respostas do motor e permite rastrear resultados e alertas até a configuração que os gerou.
- **Nomes de critérios:** a lista de `limites_calculo` (§5) vem do catálogo de cálculos. Novos critérios podem surgir em versões 1.x do motor; atualize a tela a partir do schema da versão em uso.
- **Campos reservados:** `cota_instalacao_m` (instrumento), `barragem_parametros` e `classificacao` são aceitos, mas ainda não têm efeito no motor 1.0.

<div class="quebra"></div>

## Apêndice A — `configuracao.schema.json`

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://github.com/LDTLuis/modulo-calculo-api/blob/main/docs/schemas/configuracao.schema.json",
  "title": "Configuração publicada pela Central (contrato 1.0)",
  "type": "object",
  "required": [
    "versao"
  ],
  "additionalProperties": false,
  "properties": {
    "versao": {
      "type": [
        "string",
        "integer"
      ],
      "minLength": 1,
      "description": "Revisão da configuração; devolvida em versao_config."
    },
    "fuso_padrao": {
      "type": "string",
      "pattern": "^[+-]\\d{2}:\\d{2}$",
      "default": "-03:00",
      "description": "Offset aplicado a timestamps de medição sem fuso (ex.: \"-03:00\"). Nomes de fuso não são aceitos."
    },
    "medicoes": {
      "type": "object",
      "properties": {
        "tolerancia_futuro_s": {
          "type": "number",
          "minimum": 0,
          "default": 300,
          "description": "Folga, em segundos, para aceitar leituras com horário à frente do relógio (coletores dessincronizados)."
        },
        "fator_tolerancia_lacuna": {
          "type": "number",
          "minimum": 1,
          "default": 1.5,
          "description": "Há lacuna quando o intervalo entre leituras de um instrumento passa de frequência esperada × fator."
        }
      },
      "additionalProperties": false,
      "description": "Parâmetros gerais de validação das medições (M1)."
    },
    "padroes_por_tipo": {
      "type": "object",
      "propertyNames": {
        "enum": [
          "nivel",
          "pressao",
          "vazao",
          "deslocamento"
        ]
      },
      "additionalProperties": {
        "type": "object",
        "properties": {
          "faixa": {
            "$ref": "#/$defs/faixa",
            "description": "Faixa plausível padrão do tipo."
          },
          "frequencia_esperada_s": {
            "type": "number",
            "exclusiveMinimum": 0,
            "description": "Intervalo esperado entre leituras, em segundos (detecção de lacunas)."
          }
        },
        "additionalProperties": false
      },
      "description": "Valores padrão por tipo de medição (chave: nivel, pressao, vazao ou deslocamento), usados pelos instrumentos sem valor próprio."
    },
    "sensores": {
      "type": "object",
      "additionalProperties": {
        "$ref": "#/$defs/sensor"
      },
      "description": "Cadastro por instrumento; a chave é o identificador do instrumento, igual ao campo `sensor` das medições."
    },
    "monitoramento": {
      "type": "object",
      "properties": {
        "anomalia": {
          "type": "object",
          "properties": {
            "ativo": {
              "type": "boolean",
              "default": true,
              "description": "Liga a detecção estatística."
            },
            "janela_leituras": {
              "type": "integer",
              "minimum": 3,
              "default": 24,
              "description": "Quantidade de leituras anteriores que formam a referência."
            },
            "minimo_leituras": {
              "type": "integer",
              "minimum": 3,
              "default": 8,
              "description": "Leituras anteriores mínimas para avaliar; deve ser ≤ janela_leituras."
            },
            "limiar_z": {
              "type": "number",
              "exclusiveMinimum": 0,
              "default": 3.5,
              "description": "Aciona quando |z| passa deste valor (z = 0,6745·(x − mediana)/MAD)."
            }
          },
          "additionalProperties": false,
          "description": "Detecção de leitura que destoa do comportamento recente (z-score modificado sobre mediana/MAD)."
        },
        "sensor_travado": {
          "type": "object",
          "properties": {
            "ativo": {
              "type": "boolean",
              "default": false,
              "description": "Liga a detecção de instrumento travado."
            },
            "leituras_consecutivas": {
              "type": "integer",
              "minimum": 2,
              "default": 12,
              "description": "Quantidade de valores idênticos seguidos para acionar."
            }
          },
          "additionalProperties": false,
          "description": "Detecção de valor idêntico repetido. Desligada por padrão: com leitura manual, repetições são comuns."
        }
      },
      "additionalProperties": false,
      "description": "Parâmetros gerais das regras de qualidade de dados (M2)."
    },
    "limites_calculo": {
      "type": "object",
      "properties": {
        "borda_livre_min": {
          "type": "number",
          "exclusiveMinimum": 0,
          "default": 1.0,
          "description": "Borda livre mínima acima do NA máximo (m)",
          "x-calculos": [
            "geometria.borda_livre"
          ]
        },
        "cri_limite_alto": {
          "type": "number",
          "exclusiveMinimum": 0,
          "default": 60.0,
          "description": "CRI a partir do qual a categoria de risco é ALTA",
          "x-calculos": [
            "classificacao.risco"
          ]
        },
        "cri_limite_medio": {
          "type": "number",
          "exclusiveMinimum": 0,
          "default": 35.0,
          "description": "CRI acima do qual a categoria de risco é MÉDIA",
          "x-calculos": [
            "classificacao.risco"
          ]
        },
        "dpa_limite_alto": {
          "type": "number",
          "exclusiveMinimum": 0,
          "default": 16.0,
          "description": "DPA a partir do qual o dano potencial é ALTO",
          "x-calculos": [
            "classificacao.risco"
          ]
        },
        "dpa_limite_medio": {
          "type": "number",
          "exclusiveMinimum": 0,
          "default": 10.0,
          "description": "DPA acima do qual o dano potencial é MÉDIO",
          "x-calculos": [
            "classificacao.enquadramento_pnsb",
            "classificacao.risco"
          ]
        },
        "ec_item_risco_alto": {
          "type": "number",
          "exclusiveMinimum": 0,
          "default": 10.0,
          "description": "Pontuação de um item de EC que torna o risco ALTO automaticamente",
          "x-calculos": [
            "classificacao.risco"
          ]
        },
        "fator_filtro_terzaghi": {
          "type": "number",
          "exclusiveMinimum": 0,
          "default": 5.0,
          "description": "Fator dos critérios de filtro de Terzaghi",
          "x-calculos": [
            "percolacao.filtro_terzaghi"
          ]
        },
        "fs_min_deslizamento": {
          "type": "number",
          "exclusiveMinimum": 0,
          "default": 1.5,
          "description": "Fator de segurança n contra escorregamento (P·f ≥ E·n)",
          "x-calculos": [
            "estabilidade.gravidade_deslizamento"
          ]
        },
        "fs_min_piping": {
          "type": "number",
          "exclusiveMinimum": 0,
          "default": 1.5,
          "description": "FS mínimo contra areia movediça/piping (i_crit / i_saída)",
          "x-calculos": [
            "percolacao.piping"
          ]
        },
        "fs_min_talude": {
          "type": "number",
          "exclusiveMinimum": 0,
          "default": 1.5,
          "description": "FS mínimo de estabilidade de taludes (NBR 11.682)",
          "x-calculos": [
            "estabilidade.talude_fellenius",
            "estabilidade.talude_bishop"
          ]
        },
        "largura_min_crista": {
          "type": "number",
          "exclusiveMinimum": 0,
          "default": 2.5,
          "description": "Largura mínima da crista (m)",
          "x-calculos": [
            "geometria.secao_macico"
          ]
        },
        "relacao_min_agua_terra": {
          "type": "number",
          "exclusiveMinimum": 0,
          "default": 3.0,
          "description": "Relação mínima volume de água : volume de terra",
          "x-calculos": [
            "geometria.volume_terra"
          ]
        },
        "talude_min_jusante": {
          "type": "number",
          "exclusiveMinimum": 0,
          "default": 2.0,
          "description": "Inclinação mínima recomendada do talude de jusante (H:V)",
          "x-calculos": [
            "geometria.secao_macico"
          ]
        },
        "talude_min_montante": {
          "type": "number",
          "exclusiveMinimum": 0,
          "default": 3.0,
          "description": "Inclinação mínima recomendada do talude de montante (H:V)",
          "x-calculos": [
            "geometria.secao_macico"
          ]
        },
        "zas_distancia_max_km": {
          "type": "number",
          "exclusiveMinimum": 0,
          "default": 10.0,
          "description": "Extensão máxima da ZAS a jusante (km)",
          "x-calculos": [
            "emergencia.zas"
          ]
        },
        "zas_tempo_chegada_min": {
          "type": "number",
          "exclusiveMinimum": 0,
          "default": 30.0,
          "description": "Tempo de chegada da onda que delimita a ZAS (min)",
          "x-calculos": [
            "emergencia.zas"
          ]
        }
      },
      "additionalProperties": false,
      "description": "Critérios de aceitação dos cálculos (M4+)."
    },
    "barragem_parametros": {
      "description": "Reservado (M3–M7); aceito e ainda não usado."
    },
    "classificacao": {
      "description": "Reservado (M8); aceito e ainda não usado."
    }
  },
  "$defs": {
    "faixa": {
      "type": "object",
      "properties": {
        "min": {
          "type": [
            "number",
            "null"
          ],
          "description": "Limite inferior (null = aberto)."
        },
        "max": {
          "type": [
            "number",
            "null"
          ],
          "description": "Limite superior (null = aberto)."
        },
        "unidade": {
          "enum": [
            "L/h",
            "L/min",
            "L/s",
            "MPa",
            "Pa",
            "bar",
            "cm",
            "kPa",
            "km",
            "m",
            "m3/h",
            "m3/s",
            "mca",
            "mm",
            "psi"
          ],
          "description": "Unidade de min/max; compatível com o tipo do instrumento. Padrão: unidade canônica do tipo."
        }
      },
      "additionalProperties": false,
      "description": "Faixa plausível do instrumento; min ≤ max; unidade compatível com o tipo (padrão: canônica).",
      "anyOf": [
        {
          "required": [
            "min"
          ]
        },
        {
          "required": [
            "max"
          ]
        }
      ]
    },
    "niveis": {
      "type": "object",
      "properties": {
        "aviso": {
          "type": [
            "number",
            "null"
          ],
          "description": "Valor que aciona AVISO (null ou ausente = não avaliado)."
        },
        "alerta": {
          "type": [
            "number",
            "null"
          ],
          "description": "Valor que aciona ALERTA (null ou ausente = não avaliado)."
        },
        "critico": {
          "type": [
            "number",
            "null"
          ],
          "description": "Valor que aciona CRITICO (null ou ausente = não avaliado)."
        }
      },
      "additionalProperties": false,
      "description": "Ao menos um nível; acima: aviso ≤ alerta ≤ critico; abaixo: aviso ≥ alerta ≥ critico.",
      "minProperties": 1
    },
    "sensor": {
      "type": "object",
      "properties": {
        "tipo": {
          "enum": [
            "nivel",
            "pressao",
            "vazao",
            "deslocamento"
          ],
          "description": "Tipo cadastrado; leituras desse instrumento com outro tipo são rejeitadas (TIPO_DIVERGENTE)."
        },
        "faixa": {
          "$ref": "#/$defs/faixa",
          "description": "Faixa plausível do instrumento (ficha técnica). Fora dela, a leitura é mantida com a flag FORA_FAIXA_PLAUSIVEL."
        },
        "frequencia_esperada_s": {
          "type": "number",
          "exclusiveMinimum": 0,
          "description": "Intervalo esperado entre leituras deste instrumento, em segundos; prevalece sobre o padrão do tipo."
        },
        "limites_alerta": {
          "type": "object",
          "properties": {
            "unidade": {
              "enum": [
                "L/h",
                "L/min",
                "L/s",
                "MPa",
                "Pa",
                "bar",
                "cm",
                "kPa",
                "km",
                "m",
                "m3/h",
                "m3/s",
                "mca",
                "mm",
                "psi"
              ],
              "description": "Unidade dos níveis; padrão: unidade canônica do tipo."
            },
            "acima": {
              "$ref": "#/$defs/niveis",
              "description": "Aciona quando o valor é ≥ nível. Ordem: aviso ≤ alerta ≤ critico."
            },
            "abaixo": {
              "$ref": "#/$defs/niveis",
              "description": "Aciona quando o valor é ≤ nível. Ordem: aviso ≥ alerta ≥ critico."
            }
          },
          "additionalProperties": false,
          "anyOf": [
            {
              "required": [
                "acima"
              ]
            },
            {
              "required": [
                "abaixo"
              ]
            }
          ],
          "description": "Limites de engenharia (RF-06), cadastrados pelo engenheiro; geram alertas de SEGURANCA."
        },
        "taxa_variacao": {
          "type": "object",
          "properties": {
            "unidade": {
              "enum": [
                "L/h",
                "L/min",
                "L/s",
                "MPa",
                "Pa",
                "bar",
                "cm",
                "kPa",
                "km",
                "m",
                "m3/h",
                "m3/s",
                "mca",
                "mm",
                "psi"
              ],
              "description": "Unidade da variação; padrão: unidade canônica do tipo."
            },
            "intervalo_s": {
              "type": "number",
              "exclusiveMinimum": 0,
              "default": 86400.0,
              "description": "Intervalo de referência da taxa, em segundos (86400 = por dia)."
            },
            "direcao": {
              "enum": [
                "subida",
                "descida",
                "ambas"
              ],
              "default": "ambas",
              "description": "Sentido avaliado: subida, descida ou ambas."
            },
            "aviso": {
              "type": "number",
              "exclusiveMinimum": 0,
              "description": "Variação no intervalo que aciona AVISO."
            },
            "alerta": {
              "type": "number",
              "exclusiveMinimum": 0,
              "description": "Variação no intervalo que aciona ALERTA."
            },
            "critico": {
              "type": "number",
              "exclusiveMinimum": 0,
              "description": "Variação no intervalo que aciona CRITICO."
            }
          },
          "additionalProperties": false,
          "anyOf": [
            {
              "required": [
                "aviso"
              ]
            },
            {
              "required": [
                "alerta"
              ]
            },
            {
              "required": [
                "critico"
              ]
            }
          ],
          "description": "Velocidade máxima de variação entre leituras consecutivas (ex.: rebaixamento rápido do NA)."
        },
        "cota_instalacao_m": {
          "type": "number",
          "description": "Reservado (M3); aceito e ainda não usado."
        }
      },
      "additionalProperties": false,
      "required": [
        "tipo"
      ]
    }
  }
}
```
