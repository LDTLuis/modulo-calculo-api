# Back do Desktop — Decisões iniciais e guia de integração com o motor

Registro de 30/09/2026 · motor de cálculo **v1.0.1** · contrato JSON **1.0**

Ponto de partida para implementar o back do Desktop DAMIQ, feito em outro chat. Reúne o que foi decidido, o que continua em aberto e tudo o que o back precisa saber para integrar o motor de cálculo.

---

## 1. Decisões tomadas

| Tema | Decisão |
|---|---|
| **Primeira entrega do back** | **Integração com o motor de cálculo**, antes da autenticação (RF-01) e dos cadastros completos (RF-02) |
| **Repositório** | Novo repositório **`damiq-desktop`**, **público** no GitHub (`LDTLuis/damiq-desktop`), no mesmo padrão do `modulo-calculo-api` |
| **Fluxo de trabalho** | Igual ao do motor: uma branch por entrega, PR para a `main`, CI com testes em Ubuntu e Windows (RNF-06) |
| **Stack** | A oficial (planilha *Stack DAMIQ*): Java 21 LTS, Gradle, Spring Context, Spring Events, Spring Scheduling, SQLite JDBC, Jackson, SLF4J + Logback, JUnit 5 + Mockito, OpenPDF, Apache POI |
| **Build** | **Gradle Wrapper** (`gradlew`) versionado no repositório. O Gradle não está instalado na máquina, e o wrapper garante a mesma versão para a equipe e o CI. O JDK 21 já está instalado (`jdk-21.0.11`) |
| **Arquitetura** | DDD + hexagonal, como no motor: domínio sem dependências de infraestrutura; o motor, o SQLite e a Central entram como *adapters* |

## 2. Em aberto

| Tema | Recomendação | Situação |
|---|---|---|
| JavaFX no mesmo repositório do back? | **Mesmo repositório, módulo Gradle separado (`ui/`)**. É um único aplicativo, front e back rodam no mesmo processo (Spring Context); repositórios separados exigiriam publicar o back a cada mudança de interface | A confirmar com o Pedro (front-end) |
| Empacotamento do motor no instalador | PyInstaller (executável) ou Python portátil + wheel | **Adiado** até o back existir — [issue #14](https://github.com/LDTLuis/modulo-calculo-api/issues/14) |
| API da Central (sincronização da configuração) | Cliente REST no módulo `infraestrutura` | Aguarda a Central existir. Até lá, a configuração pode vir de um arquivo JSON local |
| Pendências de engenharia (professor) | — | Tabelas e faixas CRI/DPA, níveis de alerta, FS mínimo de piping (ver `CHANGELOG.md`) |

## 3. Estrutura proposta

```
damiq-desktop/
├── dominio/          # entidades e regras: Barragem, Instrumento, Medicao, Alerta, Configuracao
│                     # sem Spring, sem JDBC, sem Jackson
├── aplicacao/        # casos de uso e portas (interfaces)
│                     #   ex.: ProcessarMedicoes, CalcularEngenharia, AtualizarConfiguracao
│                     #   portas: MotorCalculo, RepositorioMedicoes, RepositorioAlertas, FonteConfiguracao
├── infraestrutura/   # adapters: MotorCalculoProcessBuilder, repositórios SQLite (JDBC + Flyway),
│                     #   DTOs gerados do JSON Schema, cliente REST da Central (futuro)
└── ui/               # JavaFX + FXML + MVVM (front); depende apenas de `aplicacao`
```

Regras de dependência (garantidas pelo Gradle):
- `dominio` não depende de nenhum outro módulo.
- `aplicacao` depende só de `dominio`.
- `infraestrutura` depende de `aplicacao` e `dominio`.
- `ui` depende só de `aplicacao`.
- A montagem (Spring Context) fica num módulo ou pacote de inicialização, que conhece todos.

## 4. Escopo da primeira entrega (integração com o motor)

1. Esqueleto Gradle multi-módulo, com o wrapper e o CI (GitHub Actions: Ubuntu + Windows, JDK 21).
2. **Domínio mínimo:** barragem, instrumento (o campo `sensor` do contrato), medição, alerta, severidade (OK/AVISO/ALERTA/CRITICO) e versão da configuração.
3. **Porta `MotorCalculo`** e adapter **`MotorCalculoProcessBuilder`** (seção 5).
4. **DTOs Java a partir dos JSON Schemas** da release: `requisicao`, `resposta`, `configuracao`, `calculos`.
5. **Caso de uso `ProcessarMedicoes`:** registrar ou importar medições → montar `processar_lote` com a configuração vigente e o histórico → chamar o motor → gravar medições normalizadas, rejeições, lacunas e alertas no SQLite.
6. **Caso de uso `AtualizarConfiguracao`:** receber uma configuração (por enquanto de um arquivo local) → `validar_configuracao` → gravar se for válida.
7. **Testes:** unitários (Mockito na porta do motor) e **de integração que executam o motor real** instalado a partir da release.

Fica **fora** desta entrega: autenticação e perfis (RF-01), relatórios PDF (RF-07), telas JavaFX, sincronização com a Central e empacotamento.

## 5. Integração com o motor — o que o back precisa saber

Referências completas:
- **contrato:** [`docs/contrato.md`](../contrato.md);
- **schemas:** [`docs/schemas/`](../schemas/);
- **documentação em PDF:** anexada à [release v1.0.1](https://github.com/LDTLuis/modulo-calculo-api/releases/tag/v1.0.1).

### 5.1 Como obter o motor (desenvolvimento)

Até o empacotamento ([issue #14](https://github.com/LDTLuis/modulo-calculo-api/issues/14)), o motor roda num ambiente Python com o wheel da release:

```bash
py -3.13 -m venv .motor
.motor/Scripts/python -m pip install https://github.com/LDTLuis/modulo-calculo-api/releases/download/v1.0.1/damiq_calc-1.0.1-py3-none-any.whl
```

O caminho do executável Python fica **configurável** (ex.: `damiq.motor.python=...`). Quando o empacotamento existir, muda apenas o comando.

### 5.2 Chamada

```java
Process p = new ProcessBuilder(python, "-m", "damiq_calc", "--entrada", req.toString(), "--saida", resp.toString())
        .redirectError(ProcessBuilder.Redirect.PIPE)   // stderr: traceback em caso de erro interno
        .start();
int codigo = p.waitFor();   // aplicar timeout (ex.: 60 s) e destruir o processo se passar
```

- **Entrada e saída:** por arquivo (`--entrada`/`--saida`) ou por stdin/stdout, **sempre UTF-8**.
- **Códigos de saída:**

  | Código | Significado |
  |---|---|
  | `0` | sucesso |
  | `1` | entrada inválida; ler `erros[]`, cada um com `codigo`, `mensagem` e `campo` |
  | `2` | erro interno; a resposta JSON sai mesmo assim, e o traceback vai no stderr, que deve ir para o log |

- **Tempo medido por chamada:** ≈ 0,4 s, ou ≈ 1,3 s quando gera gráficos. Evite chamar o motor na thread da interface.

### 5.3 Operações

| Operação | Uso no back |
|---|---|
| `info` | Na inicialização: conferir `motor.versao` (esperado 1.0.x) e `versao_contrato` (1.x) |
| `validar_configuracao` | Antes de gravar uma configuração nova. Se inválida, **manter a anterior** e registrar o erro (`erros[].campo`) |
| `processar_lote` | Medições digitadas ou importadas (RF-03/RF-04). Enviar `configuracao` + `historico` (as últimas leituras de cada instrumento, no mínimo 24) + `medicoes` |
| `listar_calculos` | Descobrir os campos, as unidades e os limites de cada cálculo (telas de cálculo) |
| `calcular` | Cálculos de engenharia com os valores digitados na tela; a resposta traz o resultado e a memória de cálculo para o laudo |

### 5.4 Regras que o back deve seguir

- **Configuração:** a configuração inteira vai em toda chamada, e `versao_config` volta na resposta. Guarde-a junto com os resultados e alertas (auditoria, RF-12).
- **Avisos:** registre `avisos[]` (campos de configuração não reconhecidos) no log.
- **Medições:** rejeições por registro (`rejeicoes[]`) **não** reprovam o lote (saída 0). Mostre ao técnico o índice da linha e o motivo.
- **Alertas:** cada alerta é um **episódio**, com `inicio`, `fim`, `leituras` e a maior severidade. `categoria` SEGURANCA compõe `status_barragem`; QUALIDADE compõe `status_dados`. `monitoramento.nivel_resposta` traz o nível do PAE e as ações recomendadas.
- **Leitura suspeita:** com `leitura_suspeita: true`, peça verificação do instrumento antes de acionar o PAE.
- **Respostas e campos novos:** ignore campos desconhecidos nas respostas (Jackson: `FAIL_ON_UNKNOWN_PROPERTIES = false`); versões 1.x podem acrescentar campos.
- **Gráficos para relatórios:** `opcoes.graficos = {"diretorio", "formato"}` gera PNG/SVG, e os caminhos voltam em `graficos[]`, prontos para o OpenPDF.
- **Terminologia:** o conceito é *instrumento* (ponto de medição lido pelo técnico), mas no JSON os campos se chamam `sensor`, `sensores` e `sensor_travado`.

## 6. Referências

| Material | Onde |
|---|---|
| Contrato JSON 1.0 | `docs/contrato.md` (repositório do motor) e PDF na release |
| JSON Schemas | `docs/schemas/*.schema.json` e anexos da release |
| Guia da configuração (Central) | `docs/central/guia-configuracao.pdf` |
| Módulos do motor e validação | `docs/modulos-motor-calculo.md` |
| Requisitos | `Documento_de_Requisitos_DAMIQ_V1` (RF-01 a RF-13, RNF-01 a RNF-07) |
| Stack oficial | `Stack DAMIQ.xlsx` |
