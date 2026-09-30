# Motor de Cálculo DAMIQ — Módulos Revisados

Versão 0.1 · 30/09/2026 · substitui a "Tabela de Cálculos Essenciais Barragens" inicial.

**Fontes:**
- **[AP]** Apostila BCST (Prof. Elias Toledo, UNIGOIÁS 2022-1)
- **[PAE]** PSB Barragem do Ribeirão João Leite, Vol. 06 (SANEAGO, 2019)
- **[REQ]** Documento de Requisitos DAMIQ v1.0
- **[LIT]** Literatura técnica fora do material do professor. Esses cálculos ficam marcados como opcionais.

**Prioridade:**
- **P1:** MVP, exigido pelo RF-04 e RF-06
- **P2:** 2ª entrega
- **P3:** opcional

---

## 1. Princípios de arquitetura

A arquitetura segue a stack oficial: DDD, hexagonal e modularização por área da engenharia.

- **Domínio puro.** Cada área da engenharia é um pacote com funções/objetos sem I/O e com unidades SI internas. Esse código não depende de JSON, de arquivos nem de banco.
- **Adapter de entrada (CLI JSON).** O Desktop Java chama o motor via `ProcessBuilder`. O motor lê um JSON (stdin ou arquivo), executa e devolve JSON no stdout. O código de saída é `0` em caso de sucesso, `1` para erro de validação e `2` para erro interno.
- **Todo resultado traz:** valor, unidade, status (`OK`/`AVISO`/`ALERTA`/`CRITICO`), limite usado, premissas e fonte (ex.: `"AP, Nota 11"`). Isso rastreia o cálculo até o laudo e o relatório.
- **Limites parametrizáveis.** Os valores de referência (FS ≥ 1,5, faixas do ID etc.) são defaults que podem ser sobrescritos por barragem, vindos da configuração da Central Web.
- **Desempenho (RNF-01).** Um lote de 500 medições deve levar menos de 30 s. As operações ficam vetorizadas com NumPy/Pandas.

```
damiq_calc/
├── adapters/        # cli.py (JSON in/out), schemas (validação do contrato)
├── core/            # unidades, resultado/status, constantes (γw = 9,81 kN/m³…)
├── medicoes/        # M1 validação e normalização
├── monitoramento/   # M2 limites, anomalias, severidade
├── hidrostatica/    # M3 pressões, empuxo, subpressão, piezometria
├── percolacao/      # M4 rede de fluxo, gradiente, piping, filtros
├── estabilidade/    # M5 taludes e barragens de gravidade
├── hidrologia/      # M6 volume, vazões, Racional, Tr, índice de demanda
├── geometria/       # M7 maciço, crista, taludes, volume de terra
├── classificacao/   # M8 PNSB, CRI, DPA, matriz, periodicidade
├── emergencia/      # M9 nível de resposta, ZAS, estudos de ruptura importados
├── graficos/        # M10 Matplotlib para relatórios
└── opcionais/       # M11 evapotranspiração, balanço hídrico, vertedor…
```

---

## 2. Módulos

### M0 — Núcleo (`core`) · P1
Módulo de suporte usado por todos os demais.

- **Unidades.** Conversões kPa ↔ mca ↔ bar ↔ psi, m³/s ↔ L/s ↔ m³/h, mm ↔ m, cm/s ↔ m/s, ha ↔ km² ↔ m², hm³ ↔ m³. [REQ RF-04]
- **Constantes.** γw = 9,81 kN/m³, com a opção de 10 kN/m³, que é o valor usado nos exemplos da apostila.
- **Modelo de resultado.** Define o objeto `Resultado` e a escala de severidade usada por todos os módulos.

### M1 — Medições: validação e normalização (`medicoes`) · P1
Fonte: [REQ RF-03, RF-04], R-01.

| Cálculo | Regra | Entradas | Saídas |
|---|---|---|---|
| Validação de esquema | Obrigatórios: timestamp, tipo ∈ {nível, pressão, vazão, deslocamento}, valor, unidade, sensor | Lote CSV/XLSX já parseado | Registros válidos e lista de rejeições com motivo |
| Normalização | Conversão para a unidade canônica do tipo (nível → m, pressão → kPa, vazão → m³/s, deslocamento → mm) | Registro + unidade | Valor canônico |
| Consistência física | Faixa plausível por tipo/sensor, timestamp não futuro, duplicatas, ordenação | Registros + metadados do sensor | Flags de qualidade |
| Lacunas | Intervalo entre leituras maior que a frequência esperada | Série por sensor | Lista de lacunas |

### M2 — Monitoramento: limites e anomalias (`monitoramento`) · P1
Fonte: [REQ RF-04, RF-06]. O material do professor não traz métodos estatísticos, que são escolha de engenharia do time. A escala de níveis vem de [AP Lei 12.334 Art. 27] e [PAE Quadro 5.2].

| Cálculo | Regra | Saídas |
|---|---|---|
| Limites por barragem/sensor | Comparação com os limites configurados de Aviso, Alerta e Crítico (RF-06) | Severidade por leitura |
| Taxa de variação | Δvalor/Δt acima do limite (ex.: subida rápida de piezômetro, rebaixamento rápido do NA) | Severidade |
| Desvio estatístico | Z-score robusto (mediana/MAD) em janela móvel | Leituras anômalas |
| Sensor travado/ruído | Variância ≈ 0 por N leituras, ou saltos isolados | Flag de sensor |
| Consolidação | Maior severidade entre os módulos → status da barragem | Status + eventos para auditoria (RF-12) |

**Mapeamento de severidade proposto** (a confirmar com o professor):

| DAMIQ | Lei 12.334 (Art. 27) | PAE João Leite |
|---|---|---|
| Normal | Nível 0 | — |
| Aviso | Nível 1 | Verde |
| Alerta | Nível 2 | Amarelo |
| Crítico | Nível 3 | Vermelho |

### M3 — Hidrostática e piezometria (`hidrostatica`) · P1
Fonte: [AP Notas 07, 10 e 11]. Cobre o "cálculo de pressões" do RF-04.

| Cálculo | Fórmula | Entradas | Saídas |
|---|---|---|---|
| Pressão hidrostática | p = γw·h | Profundidade h | p (kPa) |
| Carga piezométrica a partir da leitura | h_p = p/γw; NA piezométrico = cota do sensor + h_p | Leitura (kPa), cota de instalação | h_p (m), cota piezométrica |
| Carga piezométrica em ponto | H_p = cota da equipotencial − cota do ponto | Cotas | H_p (m) |
| Empuxo hidrostático (por metro) | E = γw·h²/2, aplicado a h/3 da base; em superfície plana: F = γ·h_cg·A | h, área | E (kN/m), braço |
| Peso de água sobre paramento inclinado | W = γw·V | Geometria | W (kN/m) |
| Subpressão | U = área do diagrama de subpressão × γw (cargas a montante e a jusante na base) | Cargas, largura da base | U (kN/m) |

### M4 — Percolação e erosão interna (`percolacao`) · P1
Fonte: [AP Nota 11, slides 507–566]. Cobre o "gradiente crítico" do RF-04.

| Cálculo | Fórmula | Entradas | Saídas |
|---|---|---|---|
| Vazão pela rede de fluxo | Q = k·h·N_F/N_D (por unidade de largura) | k, h, N_F, N_D, largura | Q (m³/s/m e total) |
| Perda de carga por equipotencial | Δh = h/N_D | h, N_D | Δh |
| Gradiente de saída | i = Δh/l | Δh, l da última célula | i |
| Gradiente crítico | i_crit = (γsat − γw)/γw | γsat | i_crit (≈ 1; 0,8 no exemplo) |
| FS contra areia movediça/piping | FS = i_crit/i_saída | — | FS + status |
| Critério de filtro de Terzaghi | D15_filtro > 5·D15_solo (permeabilidade) e D15_filtro < 5·D85_solo (retenção) | Granulometrias | Aprovado/reprovado por critério |

**Pendência:** a apostila cita 1,5 como mínimo, mas chama FS = 2,2 de "relativamente baixo". O limite fica parametrizável e o default deve ser confirmado com o professor.

### M5 — Estabilidade (`estabilidade`) · P1 (simplificada) / P3 (busca)
Fonte: [AP Notas 09 e 10]. Cobre os "fatores simplificados de estabilidade" do RF-04.

| Cálculo | Fórmula | Entradas | Saídas |
|---|---|---|---|
| FS de talude — Fellenius | FS = Σ[c'·l + (W·cosα − u·l)·tanφ'] / Σ W·senα | Fatias (W, α, l, u), c', φ' | FS; limite ≥ 1,5 (NBR 11.682) |
| FS de talude — Bishop simplificado | FS = Σ{[c'·b + (W − u·b)·tanφ'] / m_α} / Σ W·senα, com m_α = cosα·(1 + tanα·tanφ'/FS) (iterativo) | Idem | FS, iterações |
| Gravidade — deslizamento | P·f ≥ E·n, com f = 0,75 e n = 1,50 ⇒ P ≥ 2E (descontando U quando houver) | P, E, U | FS e status |
| Gravidade — posição da resultante | Excentricidade de R na base; verificar se cai no terço médio | P, E, U, braços, L | e, status (compressão/tração) |
| Sensibilidade ao NA | Recalcular FS para a série de níveis medidos (liga medição → FS) | Série de NA | FS(t) |
| Busca do círculo crítico | Grade de centros e raios, mínimo FS | Geometria + estratigrafia | P3 |

### M6 — Hidrologia (`hidrologia`) · P2
Fonte: [AP Notas 03 a 06].

| Cálculo | Fórmula | Entradas | Saídas |
|---|---|---|---|
| Volume entre curvas de nível | Vₙ = (Sₙ + Sₙ₋₁)/2 · Δh; V_total = ΣVₙ | Pares cota–área | Curva cota–área–volume |
| Volume por seções | V = Σ Aᵢ·dᵢ | Áreas das seções, distâncias | V |
| Interpolação da curva | NA medido → volume armazenado / área do espelho | Curva + NA | V(t), A(t) — liga com M1 |
| Vazão medida | Q = Volume/Tempo médio | Volume coletado, tempos | Q |
| Vazão de cheia (Método Racional) | Q = C·i·A/360 (i em mm/h, A em ha; A ≤ 200 ha) | C, i, A | Q (m³/s) |
| Período de retorno | Tr = 1/[1 − (1 − R)^(1/n)] | Risco R, vida útil n | Tr (default de projeto: 1.000 anos) |
| Vazão de referência | Q_ref = Q_esp × AD | Q_esp (m³/s/km²), AD (km²) | Q_ref |
| Índice de demanda | ID = Q_consumo/Q_ref × 100% → Normal < 50 %; Alerta 50–80 %; Moderadamente crítico 80–100 %; Altamente crítico > 100 % | Q_consumo, Q_ref | ID + classe |
| Capacidade do extravasor | Q de projeto via Racional (como na apostila), comparado com a capacidade informada | Q projeto, Q capacidade | Folga, status |

**Pendência:** a apostila às vezes indica A em km² junto do /360. O motor adota ha para o /360 e converte a entrada.

### M7 — Geometria do maciço (`geometria`) · P2
Fonte: [AP Nota 02 e slides 103–110 e 415–418].

| Cálculo | Regra | Saídas |
|---|---|---|
| Verificação de taludes | Recomendado para barragens novas: 3:1 a montante e 2:1 a jusante; nas existentes, registrar a proporção medida | Conformidade |
| Largura da crista | Mínimo de 2,5 m (barragens novas) | Conformidade |
| Borda livre | Cota da crista − NA máximo; comparada com o valor de projeto (a apostila não dá fórmula) | Valor, status |
| Seção transversal | A = h·(2b + (m₁ + m₂)·h)/2 | Área |
| Volume de terra | V = Σ Aᵢ·Lᵢ (trapézios); caso particular 3:1/2:1 com b = 3 m: V = (5h² + 6h)·L/2 | Volume |

### M8 — Classificação e regulação (`classificacao`) · P1
Fonte: [AP Notas 01 e 08]: Lei 12.334/2010, Res. CNRH 143/2012 e 236/2017, IN SEMAD-GO 01/2020, Menescal.

| Cálculo | Regra | Saídas |
|---|---|---|
| Enquadramento na PNSB/SEMAD | Altura ≥ 15 m ou volume ≥ 3 hm³; faixa de 5–15 m ou 1–3 hm³; DPA médio/alto | Enquadrada (sim/não), grupo |
| Categoria de Risco (CRI) | CRI = CT + EC + PS (pontuações por item); qualquer item de EC = 10 ⇒ risco ALTO automático | CRI + faixa |
| Dano Potencial Associado (DPA) | Soma das pontuações (volume, população a jusante, impacto ambiental, socioeconômico) | DPA + faixa |
| Matriz de classificação | Linhas = CRI, colunas = DPA (Alto/Médio/Baixo) → Alto: A B C · Médio: A C D · Baixo: A D D | Classe A–D |
| Periodicidade da RPSB | A: 5 anos · B: 7 · C: 10 · D: 12 | Próxima revisão |
| Potencial de Risco (Menescal) | PR a partir de Periculosidade, Vulnerabilidade e Importância estratégica | PR |

**Pendência:** as tabelas de pontuação (CT, EC, PS, DPA e P/V/I) estão como imagens na apostila (slides 352–375). É preciso transcrevê-las manualmente para arquivos de dados (JSON/CSV versionados, editáveis pela Central Web) e validar as faixas com o professor.

### M9 — Emergência / PAE (`emergencia`) · P2
Fonte: [PAE §5 e §8] e [AP Art. 27].

| Cálculo | Regra | Saídas |
|---|---|---|
| Nível de resposta | Severidade consolidada (M2) → Nível 0–3 / verde, amarelo, vermelho, com a ação correspondente | Nível + ações do PAE |
| Delimitação da ZAS | Menor valor entre 10 km a jusante e a distância com chegada da onda em 30 min | Extensão da ZAS |
| Estudos de ruptura (importação) | Importar resultados do HEC-RAS (hidrogramas, tempos de chegada, profundidades por seção, população na ZAS). O motor **não** resolve Saint-Venant | Dados para relatório e alertas |

### M10 — Gráficos para relatórios (`graficos`) · P1
Fonte: [REQ RF-07] e stack (Matplotlib).

- Séries temporais por sensor, com faixas de limite e marcação de anomalias.
- Curva cota–área–volume, FS(t) × NA e histograma do índice de demanda.
- Saída em PNG ou SVG, com os caminhos devolvidos no JSON. O Desktop insere essas imagens no PDF via OpenPDF.

### M11 — Opcionais (`opcionais`) · P3 [LIT]
Nenhum destes cálculos está no material do professor. Só entram se houver demanda.

| Cálculo | Fórmula | Observação |
|---|---|---|
| Vazão de vertedor | Q = C_d·L·H^(3/2) | Útil para converter leitura de régua em vazão |
| Evapotranspiração | Penman-Monteith (FAO-56) | Exige dados meteorológicos |
| Balanço hídrico | ΔV/Δt = Q_in − Q_out − Q_evap − Q_perdas | Depende de M6 e da evapotranspiração |
| Pico de ruptura preliminar | Froehlich (1995): Qp = 0,607·V^0,295·h^1,24 | Apenas estimativa; o PAE usa HEC-RAS com parâmetros Eletrobrás/USACE |

**Removido da tabela original:** "Bf = 1,9·hb" (sem fonte identificável) e o hidrograma exponencial Q(t) = Qp·e^(−kt).

---

## 3. Contrato JSON (esboço)

```json
{
  "versao_contrato": "1.0",
  "operacao": "processar_lote",
  "barragem": { "id": "...", "limites": { "fs_min_talude": 1.5, "fs_min_piping": 1.5 } },
  "medicoes": [
    { "sensor": "PZ-01", "tipo": "pressao", "timestamp": "2026-09-30T08:00:00-03:00", "valor": 132.4, "unidade": "kPa" }
  ]
}
```

```json
{
  "status": "OK",
  "resultados": [
    { "calculo": "percolacao.fs_piping", "valor": 2.16, "unidade": "-", "status": "OK",
      "limite": 1.5, "premissas": ["gamma_w=10 kN/m3"], "fonte": "AP, Nota 11" }
  ],
  "alertas": [],
  "rejeicoes": [],
  "graficos": []
}
```

---

## 4. Ordem de implementação sugerida

1. **M0 + adapter CLI + M1.** O contrato com o Desktop fica testável cedo, o que mitiga o risco R-02.
2. **M2 e M3.** Fecham o fluxo medição → severidade → alerta (RF-04 e RF-06).
3. **M4, M5 (simplificada) e M8.**
4. **M10.** Relatórios.
5. **M6, M7 e M9.**
6. **M11.** Sob demanda.

Cada fórmula recebe testes com pytest usando os exemplos resolvidos da apostila como casos de referência. Exemplo: rede de fluxo com i_crit = 0,8, i = 0,37 e FS ≈ 2,2; Tr = 99.500 anos para R = 1 % e n = 1.000.

## 5. Decisões a validar com o professor/equipe

- Mapeamento Aviso/Alerta/Crítico ↔ Níveis 0–3 ↔ verde/amarelo/vermelho.
- FS mínimo de piping (1,5?) e de talude por condição de carregamento (final de construção, regime permanente, rebaixamento rápido).
- Transcrição das tabelas de pontuação CRI/DPA/Menescal.
- Unidade de área no Método Racional.
- Métodos estatísticos de anomalia e janelas padrão por tipo de sensor.
