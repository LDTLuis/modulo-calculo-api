# Repositórios do DAMIQ — convenção de nomes

Registro de 09/10/2026.

## Padrão

```
damiq-<produto>[-<camada>]
```

- **Prefixo `damiq-`**: agrupa todos os repositórios na listagem do GitHub (`LDTLuis/damiq-*`).
- **Produto**: `desktop`, `central` (Central de Configurações) ou `motor`.
- **Camada**, quando o produto tem mais de um repositório: `web` para o front-end e `api` para o back-end que expõe REST.
- Nomes em minúsculas, separados por hífen e sem acentos.

## Repositórios

| Repositório | Conteúdo | Situação |
|---|---|---|
| `damiq-desktop` | Aplicativo Desktop: back Java 21 + interface JavaFX | Criado |
| **`damiq-central-web`** | Front da Central de Configurações: React + TypeScript + Vite | A criar |
| **`damiq-central-api`** | Back da Central de Configurações: Spring Boot + PostgreSQL, API REST (OpenAPI) consumida pelo front e pelo Desktop | A criar |
| `modulo-calculo-api` | Motor de cálculo em Python (este repositório) | Fora do padrão, ver abaixo |

`front`/`back` foi descartado porque `web`/`api` descreve melhor o que cada repositório entrega. O back da Central é uma API usada por dois clientes, não só pelo front.

## Pendência: nome do motor

O motor não segue o padrão, e o sufixo `api` dá a ideia errada: ele é uma CLI (JSON na entrada e na saída, chamada via `ProcessBuilder`), não uma API HTTP. A pasta local também tem outro nome (`modulo-calculo-py`).

**Proposta:** renomear para `damiq-motor-calculo`. É melhor decidir antes de a Central passar a referenciar o motor.

Se for renomeado:

1. Renomear em *Settings → General* no GitHub. O GitHub redireciona as URLs antigas (clone, issues, releases), mas não é bom depender desse redirecionamento.
2. Atualizar o remote local: `git remote set-url origin git@github.com:LDTLuis/damiq-motor-calculo.git`.
3. Atualizar as referências a `modulo-calculo-api`: `README.md`, `docs/modulos-motor-calculo.md`, `docs/desktop/decisoes-back-desktop.md` (inclusive a URL do wheel), o `$id` em `docs/schemas/configuracao.schema.json` e o gerador de `docs/central/guia-configuracao.md`.
4. Atualizar no `damiq-desktop` qualquer URL de download do wheel ou da release.
