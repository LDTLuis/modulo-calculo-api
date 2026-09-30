# Contrato JSON do Motor de Cálculo — v1.0

Define como o Desktop chama o motor (`python -m damiq_calc`, via `ProcessBuilder`) e, na seção `configuracao`, **o formato dos parâmetros que a Central de Configurações Web cadastra e publica**.

## 1. Estrutura da requisição

```json
{
  "versao_contrato": "1.0",
  "operacao": "processar_lote",
  "barragem": { "id": "joao-leite" },
  "configuracao": { "...": "parâmetros da Central (seção 3)" },
  "opcoes": { "...": "opções desta execução (seção 4)" },
  "medicoes": [ "...dados da operação" ]
}
```

| Seção | Dono | Muda com que frequência | Conteúdo |
|---|---|---|---|
| `configuracao` | **Central Web** | Quando alguém edita um parâmetro (gera nova `versao`) | Faixas, frequências, tolerâncias, futuramente limites de alerta |
| `opcoes` | Desktop | A cada chamada | Parâmetros de execução (ex.: relógio de referência) |
| `barragem`, `medicoes` | Desktop | A cada chamada | Identificação e dados a processar |

**Fluxo:**
1. A Central salva a configuração no PostgreSQL e incrementa `versao`.
2. O Desktop baixa a configuração (REST), guarda a última versão no SQLite para funcionar offline e a envia **inteira** em toda chamada ao motor.
3. O motor não guarda estado. Ele aplica a configuração e devolve `versao_config` na resposta, para que o log registre qual versão gerou cada resultado (RF-12).

## 2. Unidades canônicas

O motor trabalha internamente nestas unidades. Toda medição e toda faixa são convertidas para elas.

| Tipo | Unidade canônica | Unidades aceitas (exemplos) |
|---|---|---|
| `nivel` | m | m, cm, mm, km |
| `pressao` | kPa | kPa, Pa, MPa, bar, psi, mca (1 mca = 9,81 kPa) |
| `vazao` | m3/s | m3/s, m3/h, L/s, L/min, L/h |
| `deslocamento` | mm | mm, cm, m |

Os nomes dos tipos aceitam acento e maiúsculas ("Pressão", "NÍVEL"). As unidades aceitam sobrescrito (`m³/s`).

## 3. Seção `configuracao` (Central Web)

```json
"configuracao": {
  "versao": 12,
  "fuso_padrao": "-03:00",
  "medicoes": {
    "tolerancia_futuro_s": 300,
    "fator_tolerancia_lacuna": 1.5
  },
  "padroes_por_tipo": {
    "pressao": { "faixa": { "min": 0, "max": 10, "unidade": "bar" }, "frequencia_esperada_s": 3600 },
    "vazao":   { "faixa": { "min": 0, "max": null, "unidade": "L/s" } }
  },
  "sensores": {
    "PZ-01": {
      "tipo": "pressao",
      "faixa": { "min": 0, "max": 500, "unidade": "kPa" },
      "frequencia_esperada_s": 3600
    },
    "RN-01": { "tipo": "nivel", "frequencia_esperada_s": 900 }
  }
}
```

A seção inteira é opcional. Sem ela, o motor usa os padrões da tabela abaixo e responde `versao_config: null`.

**Campos desconhecidos:** um campo que o motor não reconhece (ex.: `limite_alerta` no lugar de `limites_alerta`, ou `fs_min_pipping` em `limites_calculo`) **não** interrompe o processamento. Ele é ignorado e aparece em `avisos` na resposta:

```json
"avisos": [
  { "codigo": "CAMPO_DESCONHECIDO", "campo": "configuracao.sensores.PZ-01.limite_alerta",
    "mensagem": "campo não reconhecido por esta versão do motor; foi ignorado" }
]
```

O Desktop deve registrar esses avisos no log (RF-12) e, de preferência, exibi-los ao administrador. Os campos reservados (seção 3.8) são aceitos sem aviso.

### 3.1 Campos gerais

| Campo | Tipo | Obrigatório | Padrão | Regra |
|---|---|---|---|---|
| `versao` | texto ou inteiro | **sim** (se a seção existir) | — | Identifica a revisão. É devolvida em `versao_config` |
| `fuso_padrao` | texto | não | `"-03:00"` | Offset ISO aplicado a timestamps sem fuso. Nomes como "America/Sao_Paulo" **não** são aceitos |
| `medicoes.tolerancia_futuro_s` | número ≥ 0 | não | 300 | Folga, em segundos, para aceitar timestamps à frente do relógio (relógios de coletores dessincronizados) |
| `medicoes.fator_tolerancia_lacuna` | número ≥ 1 | não | 1,5 | Há lacuna quando o intervalo entre leituras passa de `frequência × fator` |

### 3.2 `padroes_por_tipo` — valores padrão por tipo de medição

A chave é o tipo (`nivel`, `pressao`, `vazao` ou `deslocamento`). Vale para todo sensor que não tenha valor próprio.

| Campo | Regra |
|---|---|
| `faixa` | Ver 3.4. Substitui a faixa embutida no motor para o tipo. Hoje a única embutida é vazão ≥ 0 |
| `frequencia_esperada_s` | Número > 0. Intervalo esperado entre leituras, usado na detecção de lacunas |

### 3.3 `sensores` — cadastro por instrumento

A chave é o identificador do sensor, igual ao campo `sensor` das medições.

| Campo | Obrigatório | Regra |
|---|---|---|
| `tipo` | **sim** | Tipo cadastrado. Leituras desse sensor com outro tipo são rejeitadas com `TIPO_DIVERGENTE` |
| `faixa` | não | Ver 3.4. Prevalece sobre `padroes_por_tipo` |
| `frequencia_esperada_s` | não | Prevalece sobre `padroes_por_tipo` |

**Prioridade:** o valor do sensor vale primeiro. Se não houver, vale o `padroes_por_tipo`, e por último o padrão embutido no motor.

### 3.4 Objeto `faixa` — faixa plausível do instrumento

```json
{ "min": 0, "max": 500, "unidade": "kPa" }
```

- `min` e `max` são número ou `null` (lado aberto). É preciso informar pelo menos um, e `min ≤ max`.
- `unidade` é opcional. Se ausente, vale a unidade canônica do tipo. Precisa ser compatível com o tipo (uma faixa em `kPa` para um sensor de nível é recusada).

> **Faixa plausível ≠ limite de alerta.** A faixa plausível descreve o que o **instrumento** consegue medir: é a ficha técnica, cadastrada pelo técnico. Uma leitura fora dela é **mantida** com a flag `FORA_FAIXA_PLAUSIVEL`, porque pode ser defeito do sensor ou evento real. Quem avalia é o monitoramento (M2). Os limites de **segurança da barragem** (Aviso/Alerta/Crítico) vão em `limites_alerta` (seção 3.5), cadastrados pelo engenheiro.

### 3.5 Regras de alerta por sensor (M2)

Ficam dentro de `sensores.<id>`, ao lado de `tipo` e `faixa`, e são cadastradas pelo engenheiro.

```json
"PZ-01": {
  "tipo": "pressao",
  "faixa": { "min": 0, "max": 500, "unidade": "kPa" },
  "limites_alerta": {
    "unidade": "mca",
    "acima":  { "aviso": 18, "alerta": 22, "critico": 26 }
  }
},
"RN-01": {
  "tipo": "nivel",
  "limites_alerta": { "abaixo": { "aviso": 745.0, "critico": 740.0 } },
  "taxa_variacao": { "unidade": "cm", "intervalo_s": 86400, "direcao": "descida", "aviso": 20, "alerta": 50 }
}
```

**`limites_alerta`: limites de engenharia (RF-06)**

| Campo | Regra |
|---|---|
| `unidade` | Opcional. Se ausente, vale a unidade canônica. Precisa ser compatível com o tipo |
| `acima` | `{aviso, alerta, critico}`. Aciona quando valor **≥** nível. Ordem obrigatória: aviso ≤ alerta ≤ critico |
| `abaixo` | `{aviso, alerta, critico}`. Aciona quando valor **≤** nível. Ordem obrigatória: aviso ≥ alerta ≥ critico |

- Informe pelo menos um de `acima`/`abaixo`, e em cada um pelo menos um nível. Os níveis omitidos não são avaliados (é possível ter só aviso e crítico).
- Os dois lados podem coexistir (ex.: NA do reservatório com limite máximo e mínimo).

**`taxa_variacao`: velocidade de variação**

| Campo | Padrão | Regra |
|---|---|---|
| `unidade` | canônica | Unidade da variação |
| `intervalo_s` | 86400 | Intervalo de referência (86400 = "por dia"; as leituras são digitadas/importadas, com dias entre elas) |
| `direcao` | `"ambas"` | `"subida"`, `"descida"` ou `"ambas"`. Ex.: `descida` no NA identifica **rebaixamento rápido**, condição crítica para a estabilidade do talude de montante (AP) |
| `aviso`/`alerta`/`critico` | — | Magnitudes positivas e crescentes. Pelo menos uma é obrigatória |

A taxa é calculada entre leituras consecutivas e extrapolada para o intervalo: 0,3 m em 2 dias = 0,15 m/dia. Leituras muito próximas amplificam o ruído, por isso o intervalo deve ser escolhido de acordo com a frequência de leitura do sensor.

### 3.6 Parâmetros gerais de monitoramento (M2)

```json
"monitoramento": {
  "anomalia":       { "ativo": true, "janela_leituras": 24, "minimo_leituras": 8, "limiar_z": 3.5 },
  "sensor_travado": { "ativo": false, "leituras_consecutivas": 12 }
}
```

| Campo | Padrão | Regra |
|---|---|---|
| `anomalia.ativo` | true | Liga a detecção estatística |
| `anomalia.janela_leituras` | 24 | Inteiro ≥ 3. Número de leituras anteriores que formam a referência |
| `anomalia.minimo_leituras` | 8 | Inteiro ≥ 3 e ≤ janela. Abaixo disso não avalia |
| `anomalia.limiar_z` | 3,5 | Z-score modificado: z = 0,6745·(x − mediana)/MAD. Aciona quando \|z\| > limiar |
| `sensor_travado.ativo` | **false** | Liga a detecção de valor repetido. Desligada por padrão: com leitura manual, valores repetidos são comuns e legítimos |
| `sensor_travado.leituras_consecutivas` | 12 | Inteiro ≥ 2. Número de valores idênticos seguidos para acionar |

> Sensores cujo valor pode ficar legitimamente constante (ex.: NA com vertedouro livre) precisam de um `leituras_consecutivas` alto, ou de `ativo: false`.

### 3.7 Critérios dos cálculos: `limites_calculo` (M4 em diante)

São os critérios de aceitação dos cálculos de engenharia, definidos pelo engenheiro responsável:

```json
"limites_calculo": { "fs_min_piping": 1.5, "fator_filtro_terzaghi": 5 }
```

- Cada chave é o nome de um limite e cada valor é um número > 0. Os nomes disponíveis e seus padrões aparecem em `listar_calculos` (campo `limites` de cada cálculo). A tela da Central pode ser montada a partir disso.
- Um limite ausente usa o padrão do motor. A memória de cálculo registra a origem ("padrão do motor" ou "configuração da Central"), para o laudo mostrar qual critério foi aplicado.
- O usuário que digita os valores **não** altera os critérios: eles vêm só da Central.

| Limite | Padrão | Usado em |
|---|---|---|
| `fs_min_piping` | 1,5 | `percolacao.piping` |
| `fator_filtro_terzaghi` | 5 | `percolacao.filtro_terzaghi` |
| `fs_min_talude` | 1,5 (NBR 11.682) | `estabilidade.talude_fellenius`, `estabilidade.talude_bishop` |
| `fs_min_deslizamento` | 1,5 (n da apostila) | `estabilidade.gravidade_deslizamento` |
| `largura_min_crista` | 2,5 m | `geometria.secao_macico` |
| `talude_min_montante` / `talude_min_jusante` | 3 / 2 (H:V) | `geometria.secao_macico` |
| `relacao_min_agua_terra` | 3 | `geometria.volume_terra` |
| `borda_livre_min` | 1,0 m | `geometria.borda_livre` |
| `cri_limite_alto` / `cri_limite_medio` | 60 / 35 | `classificacao.risco` (**conferir com as tabelas da apostila**) |
| `ec_item_risco_alto` | 10 | `classificacao.risco` |
| `dpa_limite_alto` / `dpa_limite_medio` | 16 / 10 | `classificacao.risco`, `classificacao.enquadramento_pnsb` (**conferir**) |
| `zas_distancia_max_km` / `zas_tempo_chegada_min` | 10 km / 30 min | `emergencia.zas` |

### 3.8 Campos reservados (próximas versões)

A Central já pode planejar as telas para estes campos. O motor 1.0 os aceita sem usá-los e sem gerar aviso.

| Campo (por sensor) | Módulo | Descrição prevista |
|---|---|---|
| `cota_instalacao_m` | M3 | Cota do sensor, para converter pressão em carga piezométrica |

| Campo (geral) | Módulo | Descrição prevista |
|---|---|---|
| `barragem_parametros` | M3–M7 | Geometria, γ dos materiais, cotas de crista e NA máximo |
| `classificacao` | M8 | Tabelas de pontuação CRI/DPA versionadas |

## 4. Seção `opcoes` e `historico` (Desktop, por execução)

| Campo | Regra |
|---|---|
| `opcoes.agora` | ISO 8601 **com fuso**. Relógio de referência para "timestamp no futuro". Se ausente, usa o relógio da máquina. Útil para reprocessar lotes antigos e em testes |
| `opcoes.graficos` | `{"diretorio": "...", "formato": "png" \| "svg"}` (M10). Gera uma **série temporal por sensor** do lote (histórico incluído), com as linhas de limite de alerta e as leituras fora da faixa plausível destacadas. Os caminhos voltam em `graficos: [{"tipo": "serie_temporal", "sensor", "arquivo"}]`, prontos para o Desktop embutir no PDF (OpenPDF). Também vale em `calcular` para os cálculos com gráfico (hoje, `hidrologia.curva_cota_volume` → `curva_cota_area_volume`) |
| `historico` | Lista opcional, no mesmo formato de `medicoes`, com leituras **já processadas** antes deste lote. Serve só de contexto para taxa de variação, janela estatística, sensor travado e lacuna na transição. **Não gera alertas.** Leituras com o mesmo sensor e timestamp de uma leitura do lote são descartadas |

**Quanto histórico enviar:** por sensor, no mínimo `anomalia.janela_leituras` leituras (padrão 24) ou `sensor_travado.leituras_consecutivas` (padrão 12), o que for maior. Sem histórico, o motor funciona, mas a primeira leitura de cada sensor no lote não tem taxa de variação nem referência estatística.

## 5. Resposta de `processar_lote`

```json
{
  "versao_contrato": "1.0",
  "operacao": "processar_lote",
  "status": "OK",
  "versao_config": 12,
  "resumo": { "recebidas": 3, "validas": 2, "rejeitadas": 1, "lacunas": 1, "alertas": 1,
              "historico": { "recebidas": 24, "validas": 24, "rejeitadas": 0 } },
  "monitoramento": {
    "status_barragem": "ALERTA",
    "status_dados": "OK",
    "sensores": {
      "PZ-01": { "tipo": "pressao", "status_atual": "ALERTA", "status_maximo": "ALERTA",
                 "ultima_leitura": { "timestamp": "2026-09-29T11:00:00-03:00", "valor": 230.0, "unidade": "kPa" } }
    }
  },
  "alertas": [
    { "tipo": "LIMITE", "categoria": "SEGURANCA", "sensor": "PZ-01", "severidade": "ALERTA",
      "inicio": "2026-09-29T10:00:00-03:00", "fim": "2026-09-29T11:00:00-03:00", "leituras": 2,
      "valor_extremo": 240.0, "unidade": "kPa", "limite": 215.82, "direcao": "acima",
      "leitura_suspeita": false, "detalhe": {},
      "mensagem": "PZ-01: pressao 240 kPa acima do limite de alerta (215.82 kPa) em 2 leituras" }
  ],
  "medicoes": [ { "sensor": "PZ-01", "tipo": "pressao", "timestamp": "2026-09-29T08:00:00-03:00",
                  "valor": 140.0, "unidade": "kPa", "valor_original": 1.4, "unidade_original": "bar",
                  "flags": [] } ],
  "rejeicoes": [ { "indice": 2, "codigo": "VALOR_INVALIDO", "mensagem": "Valor não numérico: 'x'" } ],
  "rejeicoes_historico": [],
  "lacunas": [ { "sensor": "PZ-01", "inicio": "...", "fim": "...", "duracao_s": 10800 } ],
  "resultados": [], "graficos": [], "erros": []
}
```

### Alertas (M2)

Cada alerta é um **episódio**: leituras consecutivas do mesmo sensor que dispararam a mesma regra viram um único alerta, com `inicio`, `fim`, número de `leituras`, `valor_extremo` e a **maior** severidade atingida.

| `tipo` | `categoria` | Severidade | Origem |
|---|---|---|---|
| `LIMITE` | SEGURANCA | Configurada em `limites_alerta` | Valor atingiu aviso/alerta/crítico |
| `TAXA_VARIACAO` | SEGURANCA | Configurada em `taxa_variacao` | Subida/descida rápida. A `unidade` vem por intervalo (ex.: `m/h`) |
| `FORA_FAIXA_PLAUSIVEL` | QUALIDADE | AVISO | Leitura fora da faixa do instrumento (provável defeito) |
| `SENSOR_TRAVADO` | QUALIDADE | AVISO | Valor idêntico repetido |
| `ANOMALIA_ESTATISTICA` | QUALIDADE | AVISO | Destoa das leituras recentes. `detalhe.z` traz o z-score |

- **`status_barragem`** é a maior severidade entre os alertas de SEGURANCA. **`status_dados`** é a maior entre os de QUALIDADE. Assim, um sensor com defeito não coloca a barragem em alerta.
- **Leitura suspeita:** uma leitura fora da faixa plausível **continua** sendo avaliada contra os limites (postura conservadora), e o alerta de limite vem com `leitura_suspeita: true`, para o operador verificar o instrumento antes de acionar o PAE.
- **Situação de cada sensor:** `status_atual` é o limite atingido na última leitura do lote (para o dashboard). `status_maximo` é o pior alerta de segurança do lote.
- **`monitoramento.nivel_resposta`** traduz o `status_barragem` no nível de resposta do PAE: `{"nivel", "cor", "rotulo", "situacao", "acoes", "fonte"}` (ex.: ALERTA → Nível 2, amarelo). O Desktop pode exibir as ações recomendadas diretamente no alerta.

Mapeamento proposto (a validar com o professor): OK ↔ Nível 0 · AVISO ↔ Nível 1 / verde · ALERTA ↔ Nível 2 / amarelo · CRITICO ↔ Nível 3 / vermelho.

### Códigos de rejeição (por registro, com status `OK` e saída 0)

`REGISTRO_INVALIDO`, `CAMPO_AUSENTE`, `SENSOR_INVALIDO`, `TIPO_INVALIDO`, `TIPO_DIVERGENTE`, `TIMESTAMP_INVALIDO`, `TIMESTAMP_FUTURO`, `VALOR_INVALIDO`, `UNIDADE_DESCONHECIDA`, `UNIDADE_INCOMPATIVEL`, `DUPLICADA`

### Erros da requisição (status `ERRO`, saída 1)

`JSON_INVALIDO`, `CONTRATO_INVALIDO` (inclui configuração inválida: a mensagem indica o campo, ex.: `'configuracao.sensores.PZ-01.faixa': min (5) maior que max (1)`), `VERSAO_INCOMPATIVEL`, `OPERACAO_DESCONHECIDA`.

Se houver falha interna, a resposta vem com `ERRO_INTERNO` e saída 2.

**Recomendação para a Central:** aplicar as mesmas regras da seção 3 na validação dos formulários (Zod + Bean Validation), para que uma configuração inválida nunca chegue ao Desktop.

## 6. Cálculos de engenharia: `listar_calculos` e `calcular` (M3–M8)

O usuário digita os valores numa tela do Desktop. O Desktop envia esses valores ao motor e exibe o resultado e a memória de cálculo. **Fórmulas, conversões, validações e limites ficam só no motor.**

### 6.1 Descoberta dos campos: `listar_calculos`

```json
{ "versao_contrato": "1.0", "operacao": "listar_calculos", "modulo": "hidrostatica" }
```

O campo `modulo` é opcional (sem ele, lista todos os cálculos). Para cada cálculo, a resposta traz o `id`, o título, a fonte e as entradas que a tela deve coletar:

```json
{
  "id": "hidrostatica.empuxo",
  "modulo": "hidrostatica",
  "titulo": "Empuxo hidrostático no paramento de montante",
  "fonte": "AP, Nota 10 – Empuxo em barramentos",
  "entradas": [
    { "nome": "altura_agua", "descricao": "Altura da lâmina d'água sobre a base (h)", "unidade": "m",
      "unidades_aceitas": ["m", "cm", "mm", "km"], "obrigatoria": true, "padrao": null,
      "minimo": 0, "minimo_inclusivo": false, "maximo": null, "inteiro": false },
    { "nome": "gama_w", "unidade": "kN/m3", "obrigatoria": false, "padrao": 9.81, "...": "..." }
  ]
}
```

O Desktop pode montar as telas a partir disso, com rótulo = `descricao` e uma lista de unidades = `unidades_aceitas`. Também pode usar essa resposta só para validar as telas feitas à mão.

### 6.2 Execução: `calcular`

```json
{
  "versao_contrato": "1.0",
  "operacao": "calcular",
  "calculo": "hidrostatica.subpressao",
  "entradas": {
    "largura_base": 56,
    "pressao_montante": { "valor": 182, "unidade": "kPa" },
    "pressao_jusante": { "valor": 7.34, "unidade": "mca" }
  }
}
```

- Cada entrada é um número (na unidade padrão do campo) ou `{"valor", "unidade"}`.
- Entradas do **tipo tabela** (`"tipo": "tabela"` na descoberta, ex.: `fatias`) recebem uma lista de linhas. Cada linha é um objeto com as colunas descritas em `colunas`, e cada célula segue a mesma regra (número ou `{"valor", "unidade"}`). Os erros apontam a célula: `"campo": "fatias[2].alfa"`.
- Campos opcionais podem ser omitidos. Quando um padrão é usado, o motor registra essa escolha em `memoria.premissas`.
- Campos que não pertencem ao cálculo são **recusados** (`CAMPO_DESCONHECIDO`), para pegar erros de digitação na integração.

**Resposta:**

```json
{
  "status": "OK",
  "calculo": { "id": "hidrostatica.subpressao", "titulo": "...", "fonte": "AP, Nota 11 – ..." },
  "entradas": { "largura_base": { "valor": 56.0, "unidade": "m" }, "...": "valores já convertidos" },
  "resultados": [
    { "calculo": "hidrostatica.subpressao.por_metro", "descricao": "Subpressão por metro",
      "valor": 7112.0, "unidade": "kN/m", "status": "OK", "limite": null, "premissas": [], "fonte": "..." }
  ],
  "memoria": {
    "passos": [
      { "descricao": "Subpressão por metro (área do diagrama trapezoidal)", "formula": "U = B · (u1 + u2) / 2",
        "substituicao": "U = 56 · (182 + 72) / 2 = 7112 kN/m", "valor": 7112.0, "unidade": "kN/m" }
    ],
    "premissas": [],
    "conclusoes": []
  },
  "status_calculo": "OK"
}
```

- `memoria.passos` é a memória de cálculo pronta para o relatório e o laudo, com texto em pt-BR e vírgula decimal.
- `memoria.premissas` lista os padrões usados e os critérios aplicados, com a origem (ex.: `"fs_min_piping = 1,5 (padrão do motor)"`).
- `memoria.conclusoes` traz o parecer em texto nos cálculos com critério (ex.: `"FS = 2,18 ≥ 1,5: atende ao critério contra areia movediça."`).
- `memoria.tabelas` traz tabelas de apoio ao relatório, como o cálculo fatia a fatia: `{"titulo", "colunas": [{"nome", "unidade"}], "linhas": [[...]]}`.
- `resultados[].rotulo` traz o texto dos resultados categóricos (ex.: classe do índice de demanda `"Moderadamente crítico"`, classe de risco `"B"`). Nos resultados numéricos, é `null`.

**Status nos cálculos com critério de segurança:** cada resultado traz `status` e `limite`, e `status_calculo` é o pior deles. Para fatores de segurança:

| FS | `status` |
|---|---|
| FS ≥ mínimo | OK |
| 1 ≤ FS < mínimo | ALERTA (não atende o critério) |
| FS < 1 | CRITICO (ruptura/instabilidade esperada) |

Critérios do tipo atende/não atende (ex.: filtro de Terzaghi) usam OK ou ALERTA.

**Erros de entrada** (saída 1) vêm com um erro por campo, para a tela destacar cada um:

```json
"erros": [
  { "codigo": "FORA_DO_INTERVALO", "mensagem": "deve ser > 0 m", "campo": "largura_base" },
  { "codigo": "CAMPO_AUSENTE", "mensagem": "campo obrigatório", "campo": "pressao_montante" }
]
```

Códigos: `CAMPO_AUSENTE`, `CAMPO_DESCONHECIDO`, `VALOR_INVALIDO`, `FORA_DO_INTERVALO`, `UNIDADE_DESCONHECIDA`, `UNIDADE_INCOMPATIVEL` e, para `calculo` inexistente, `CALCULO_DESCONHECIDO`.

### 6.3 Cálculos disponíveis

| `calculo` | Resultados | Fonte |
|---|---|---|
| `hidrostatica.pressao` | p = γw·h | AP Nota 10 |
| `hidrostatica.piezometro` | Carga (hp = u/γw) e cota piezométrica | AP Nota 11 |
| `hidrostatica.carga_rede_fluxo` | Δh, carga total, carga piezométrica e pressão em um ponto da fundação | AP Nota 11, Ex. 1 |
| `hidrostatica.empuxo` | Empuxo horizontal (γw·h²/2) e braço; com paramento inclinado, componente vertical, braço e resultante; total com comprimento | AP Nota 10 |
| `hidrostatica.subpressao` | Subpressão por metro (B·(u1+u2)/2), ponto de aplicação e total | AP Nota 11, Ex. 1 |
| `percolacao.darcy` | Gradiente i = Δh/L, velocidade v = k·i e, com área, vazão Q = k·i·A | AP Nota 11 (Lei de Darcy) |
| `percolacao.vazao_rede_fluxo` | Q = k·h·N_F/N_D por metro, e total com comprimento | AP Nota 11, slides 513 e 536 |
| `percolacao.piping` | Δh, gradiente de saída, gradiente crítico (γsat − γw)/γw e **FS contra areia movediça** (critério `fs_min_piping`) | AP Nota 11, Ex. 2 |
| `percolacao.filtro_terzaghi` | Razões D15f/D15s (> fator) e D15f/D85s (< fator), com parecer por critério | AP Nota 11 (filtros de proteção) |
| `estabilidade.talude_fellenius` | FS = Σ[c'·l + (W·cos α − u·l)·tan φ'] / Σ W·sen α, a partir da tabela `fatias`, com tabela por fatia (critério `fs_min_talude`) | AP Nota 09 (NBR 11.682) |
| `estabilidade.talude_bishop` | FS de Bishop simplificado, iterativo (m_α = cos α + sen α·tan φ'/FS), com tabela por fatia (critério `fs_min_talude`) | AP Nota 09 (NBR 11.682) |
| `estabilidade.gravidade_deslizamento` | FS = f·(P − U)/E e peso mínimo P_mín = E·n/f + U (critério `fs_min_deslizamento`; f padrão 0,75) | AP Nota 10 (P·f ≥ E·n) |
| `estabilidade.gravidade_resultante` | Resultante vertical, posição x_R, excentricidade e tensões nos pés de montante e jusante; status pelo terço médio | AP Nota 10 (categorias da resultante) |
| `hidrologia.curva_cota_volume` | Volume entre curvas de nível Vn = (Sn + Sn−1)/2·Δh, volume total e, com `cota_consulta`, área e volume nessa cota (interpolação); tabela por curva | AP Nota 03 (exemplo: 5.823 m³) |
| `hidrologia.volume_secoes` | V = Σ Aᵢ·dᵢ a partir da tabela `secoes` | AP Nota 03 |
| `hidrologia.vazao_medida` | Tempo médio das repetições e Q = Volume/Tempo médio | AP Nota 02 (vazão de base) |
| `hidrologia.metodo_racional` | Q = C·i·A/360 (i em mm/h, A em ha); AVISO se A > 200 ha (fora do domínio do método) | AP Nota 04 |
| `hidrologia.periodo_retorno` | Tr = 1/[1 − (1 − R)^(1/n)]; R aceita `%` | AP Nota 06 (Tr ≈ 99.500 e 4.480 anos) |
| `hidrologia.indice_demanda` | Qref = Qesp·AD e ID = Qconsumo/Qref·100, com `rotulo` da classe: Normal (OK), Alerta (AVISO), Moderadamente crítico (ALERTA), Altamente crítico (CRITICO) | AP Nota 01 (outorga) |
| `hidrologia.extravasor` | Relação capacidade/vazão de projeto e folga; CRITICO se a capacidade for menor que a vazão de projeto | AP Nota 02 |
| `geometria.secao_macico` | Largura da base B = b + (m₁ + m₂)·h, área da seção e conformidade de crista (≥ 2,5 m) e taludes (3:1 montante, 2:1 jusante); AVISO quando abaixo do recomendado | AP Nota 02 |
| `geometria.volume_terra` | Volume por trapézios (tabela `trechos`) e, com `volume_agua`, relação água : terra (≥ 3:1) | AP Nota 02 (exemplo: 1.336,625 m³) |
| `geometria.borda_livre` | BL = cota da crista − NA máximo; ALERTA abaixo do mínimo (1,0 m) e CRITICO se BL ≤ 0 (galgamento) | AP Nota 02 (folga de 1,0 m) |
| `classificacao.enquadramento_pnsb` | Enquadramento na PNSB (altura ≥ 15 m, capacidade ≥ 3 hm³, resíduos perigosos ou DPA médio/alto), com `rotulo` SIM/NÃO, e grupo de cadastramento SEMAD-GO (1, 2 ou 3) | AP Nota 01 (Lei 12.334/2010; IN SEMAD 01/2020) |
| `classificacao.risco` | CRI = CT + EC + PS e categoria (item de EC = 10 → ALTO automático, CRITICO); categoria do DPA; classe A–D pela matriz da apostila (Alto: A B C · Médio: A C D · Baixo: A D D); periodicidade da RPSB (A 5, B 7, C 10, D 12 anos) | AP Nota 08 (Res. CNRH 143/2012) |
| `emergencia.nivel_resposta` | Nível de resposta do PAE a partir da severidade (0–3): `rotulo` "Nível 2 – amarelo", situação e ações em `memoria.conclusoes` | AP Nota 07 (art. 27); PAE João Leite |
| `emergencia.zas` | Extensão da ZAS = mín(10 km; distância alcançada pela onda em 30 min), a partir da tabela `secoes` (distância × tempo de chegada) do estudo de ruptura; AVISO se o estudo não alcança 30 min antes de 10 km | PAE João Leite (critério ANA) |
| `opcionais.vertedor_retangular` | [LIT] Q = C·L·H^1,5 (Francis; C padrão 1,838 SI) | Literatura técnica |
| `opcionais.vertedor_triangular` | [LIT] Q = C·H^2,5 (Thomson 90°; C padrão 1,4 SI), para medidores de vazão de drenagem | Literatura técnica |
| `opcionais.evapotranspiracao_fao56` | [LIT] ET0 pelo Penman-Monteith FAO-56, passo diário (mm/dia) | FAO-56 (Exemplo 18: ≈ 3,9 mm/dia) |
| `opcionais.balanco_hidrico` | [LIT] Qevap = E·A, ΔV = (Qin − Qout − Qevap − Qperdas)·Δt e volume final (ALERTA se o reservatório esvazia) | Literatura técnica |
| `opcionais.pico_ruptura_froehlich` | [LIT] Qp = 0,607·Vw^0,295·hw^1,24, **estimativa preliminar** (o PAE usa HEC-RAS) | Froehlich (1995) |

**Convenções do M5:**
- As fatias são informadas prontas (largura, peso, α, c', φ', u). A busca automática do círculo crítico fica para uma etapa futura.
- α é positivo quando a base da fatia sobe no sentido do movimento.
- Na gravidade, as forças são por metro de barragem, as distâncias horizontais são medidas a partir do pé de montante e as alturas a partir da base. O empuxo e a subpressão podem vir direto dos resultados de `hidrostatica.empuxo` e `hidrostatica.subpressao`.
- Status da resultante: OK no terço médio (base toda comprimida), ALERTA fora do terço médio (tração em parte da base) e CRITICO fora da base (tombamento). Quando U ≥ P, o resultado é CRITICO (flutuação).

> Nas entradas em `mca`, a conversão usa 1 mca = 9,81 kPa, mesmo que o `gama_w` informado seja outro.
