# Changelog

Formato baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/); versões seguem [SemVer](https://semver.org/lang/pt-BR/).
A versão do **contrato JSON** (`versao_contrato`) é independente da versão do pacote: mudanças compatíveis mantêm o contrato 1.x.

## [1.0.0] – 2026-09-30

Primeira versão para integração com o Desktop e a Central de Configurações. Contrato JSON **1.0**.

### Operações
- `info`: versão do motor e operações disponíveis.
- `processar_lote`: validação e normalização de medições (M1), lacunas, alertas por episódio (M2), status da barragem e dos dados, nível de resposta do PAE (M9) e gráficos opcionais (M10).
- `listar_calculos` / `calcular`: 32 cálculos de engenharia (M3–M8, M11), com memória de cálculo, premissas, conclusões e tabelas.
- `validar_configuracao`: valida a configuração da Central antes de o Desktop gravá-la.

### Módulos
- **M0 Núcleo:** unidades, severidade, entradas (inclusive tabelas) com erro por campo, critérios configuráveis.
- **M1 Medições** e **M2 Monitoramento:** limites de alerta, taxa de variação, anomalia estatística, sensor travado, leituras suspeitas.
- **M3 Hidrostática**, **M4 Percolação**, **M5 Estabilidade**, **M6 Hidrologia**, **M7 Geometria**, **M8 Classificação**, **M9 Emergência**, **M10 Gráficos**, **M11 Opcionais [LIT]**.

### Integração
- Seção `configuracao` publicada pela Central, com `avisos` para campos desconhecidos e `erros[].campo` nos erros.
- JSON Schema gerado a partir do código em `docs/schemas/`.
- CI em Ubuntu e Windows (Python 3.13); release publicada a partir de tags `v*`.

### Pendências conhecidas (a validar com o professor)
- Tabelas de pontuação CT/EC/PS/DPA e faixas de corte do CRI/DPA (M8).
- Mapeamento Aviso/Alerta/Crítico ↔ Níveis 1–3 ↔ verde/amarelo/vermelho.
- FS mínimo de piping (padrão 1,5).
