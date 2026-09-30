# damiq-calc — Motor de Cálculo DAMIQ

Serviço Python chamado pelo Desktop (Java, via `ProcessBuilder`) para validar medições e executar os cálculos de segurança de barragens. Módulos planejados: [docs/modulos-motor-calculo.md](docs/modulos-motor-calculo.md).

## Ambiente

```bash
py -3.13 -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"
.venv/Scripts/python -m pytest
```

## Uso

```bash
.venv/Scripts/python -m damiq_calc --entrada requisicao.json --saida resposta.json
```

Sem `--entrada`/`--saida`, lê do stdin e escreve no stdout, sempre em UTF-8.

| Código de saída | Significado |
|---|---|
| 0 | Sucesso (a resposta pode conter `rejeicoes` de registros individuais) |
| 1 | Entrada inválida (`status: "ERRO"`, detalhes em `erros`) |
| 2 | Erro interno (traceback no stderr, resposta JSON ainda é emitida) |

Chamada do lado Java:

```java
Process p = new ProcessBuilder(pythonExe, "-m", "damiq_calc", "--entrada", req.toString(), "--saida", resp.toString())
        .directory(motorDir.toFile())
        .start();
int codigo = p.waitFor();
```

## Operações (contrato 1.0)

Especificação completa, incluindo a seção `configuracao` publicada pela Central Web: [docs/contrato.md](docs/contrato.md).

- `info` — versão do motor e operações disponíveis (handshake).
- `listar_calculos` / `calcular` — M3+: descoberta dos campos de cada cálculo e execução com memória de cálculo.
- `processar_lote` — M1: valida, normaliza para a unidade canônica do tipo (nível → m, pressão → kPa, vazão → m3/s, deslocamento → mm) e detecta lacunas; M2: gera alertas (limites, taxa de variação, qualidade) e o status da barragem e dos dados.

```json
{
  "versao_contrato": "1.0",
  "operacao": "processar_lote",
  "barragem": { "id": "joao-leite" },
  "configuracao": {
    "versao": 12,
    "sensores": {
      "PZ-01": { "tipo": "pressao", "faixa": { "min": 0, "max": 500, "unidade": "kPa" }, "frequencia_esperada_s": 3600 }
    }
  },
  "medicoes": [
    { "sensor": "PZ-01", "tipo": "pressao", "timestamp": "2026-09-29T08:00:00-03:00", "valor": 132.4, "unidade": "kPa" }
  ]
}
```

## Estrutura

```
src/damiq_calc/
├── adapters/   # cli.py (entrada/saída), contrato.py (operações), configuracao.py (seção da Central)
├── core/       # M0: unidades, constantes, erros, Resultado/Severidade
├── medicoes/   # M1: modelo, validação, lacunas
├── monitoramento/  # M2: regras (limites, taxa, z-score, travado), avaliação por episódios
├── hidrostatica/   # M3: pressão, piezômetro, cargas na rede de fluxo, empuxo, subpressão
├── percolacao/     # M4: Darcy, vazão pela rede de fluxo, piping (FS), filtros de Terzaghi
├── estabilidade/   # M5: taludes (Fellenius, Bishop) e gravidade (escorregamento, terço médio)
├── hidrologia/     # M6: cota–área–volume, vazões, Método Racional, Tr, índice de demanda, extravasor
└── geometria/      # M7: seção do maciço, crista e taludes, volume de terra, borda livre
# core/calculo.py: entradas, memória de cálculo e registro dos cálculos; catalogo.py: índice
```

## Fluxo de trabalho

- Uma branch por módulo ou tarefa (`feature/m5-estabilidade`, `chore/...`), integrada à `main` por pull request.
- O GitHub Actions ([.github/workflows/testes.yml](.github/workflows/testes.yml)) roda o pytest em Ubuntu e Windows com Python 3.13 em todo PR e em cada push na `main`.
