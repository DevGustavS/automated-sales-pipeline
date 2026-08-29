# Automated Sales Pipeline

Pipeline local e reproduzível para receber, validar, consolidar e disponibilizar os dados fictícios de vendas do desafio **Automated Sales Pipeline — 20260825**.

**Estado atual:** a Fase 2A estabiliza a ingestão segura existente, o tratamento em Pandas, as regras de qualidade, a persistência em DuckDB/Parquet, a quarentena, o dashboard Streamlit e a exportação CSV. Não há cloud, Docker, banco externo, autenticação ou MCP.

## Mapeamento do desafio

| Requisito | Implementação atual | Verificação |
| --- | --- | --- |
| Receber os arquivos | `pipeline.py` aceita ZIP, CSV ou diretório local, valida formato e não modifica a origem. | Testes de ingestão segura e hash do ZIP. |
| Compreender e relacionar estruturas | Quatro schemas conhecidos são consolidados; vendas são relacionadas a consultores, lojas e veículos. | Testes de schema, joins e integridade referencial. |
| Identificar qualidade | Catálogo explícito com 18 regras, severidade, condição, tratamento e motivo. | `quality_report.csv`, tabela `quality_report` e testes artificiais. |
| Realizar tratamentos | Limpeza textual, IDs normalizados, três formatos de data, dinheiro decimal, deduplicação e cálculo de descontos. | Testes de datas, centavos, duplicatas e resultados reais. |
| Consolidar informações | Fato de vendas, dimensões e mart mensal persistidos em DuckDB local. | Contagens e agregações consultadas após cada execução controlada. |
| Gerar camada analítica | `fact_sales_pipeline.parquet`, tabelas DuckDB e relatório de qualidade. | Schema monetário `DECIMAL`, leitura DuckDB e Parquet testadas. |
| Permitir reexecuções | CLI com destinos explícitos, staging e publicação com rollback. | Duas execuções produzem o mesmo conteúdo lógico e os mesmos hashes de CSV/Parquet. |
| Disponibilizar análise | Dashboard Streamlit com KPIs, filtros, gráficos, qualidade, dados e download. | Teste do caso vazio e validação local do dashboard. |
| Organizar e documentar | Estrutura simples, comandos Windows, segurança, dependências e uso de IA documentados. | Pytest, Ruff, pip-audit e `git diff --check`. |

## Arquitetura

```text
ZIP/CSV/diretório (somente leitura)
        |
        v
pipeline.py: descoberta, limites, schemas e rastreabilidade
        |
        v
build_pipeline.py: normalização, regras, joins e métricas
        |
        +--> data/output/       DuckDB, Parquet e quality_report.csv
        +--> data/quarantine/   rejected_sales.csv
                    |
                    +--> dashboard.py / export_csv.py
```

Os artefatos são gerados primeiro em diretórios temporários no mesmo volume. A publicação usa substituições de arquivo e restaura a versão anterior se uma substituição falhar durante o processo.

## Estrutura relevante

```text
.
├── data/
│   ├── incoming/       # entrada original local e imutável
│   ├── output/         # banco, Parquet e relatório gerados
│   ├── processed/      # reservado para derivados futuros
│   └── quarantine/     # vendas rejeitadas
├── docs/
│   ├── challenge.md
│   └── dashboard_preview.png
├── tests/
├── build_pipeline.py
├── dashboard.py
├── export_csv.py
├── pipeline.py
├── requirements.txt
└── SECURITY.md
```

Dados, bancos e resultados são ignorados pelo Git; somente os arquivos `.gitkeep` preservam os diretórios.

## Entrada e ingestão segura

O pacote original esperado é:

```text
data/incoming/Teste_Tecnico_Dados_Candidato_20260825.zip
```

SHA-256 conhecido:

```text
06BE13B4E818849568965B0E3E7BA64F9EDC78BE8D8207C9A088C35773D60DAD
```

A ingestão aceita UTF-8 com ou sem BOM e delimitador `;`. Ela valida os schemas exatos de `consultores`, `lojas`, `veiculos` e `vendas`, preserva todas as colunas recebidas como texto e adiciona `__source_file` e `__source_line` em memória. ZIP Slip, links, junctions, arquivos especiais, colisões de caminhos, conteúdo inesperado, CRC, compressão e limites de tamanho são verificados antes do uso.

Inspeção sem gerar outputs:

```powershell
.\.venv\Scripts\python.exe pipeline.py inspect "data\incoming\Teste_Tecnico_Dados_Candidato_20260825.zip"
```

## Ambiente no Windows

Pré-requisito: Python 3.14.5. Confirme a versão antes de criar o ambiente:

```powershell
python --version
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Não é necessário ativar a `.venv`; os comandos usam o executável diretamente. Se uma `.venv` existente mostrar outra versão, recrie-a somente após preservar qualquer configuração local necessária.

## Executar o pipeline

```powershell
.\.venv\Scripts\python.exe build_pipeline.py `
  "data\incoming\Teste_Tecnico_Dados_Candidato_20260825.zip" `
  --output "data\output" `
  --quarantine "data\quarantine"
```

Saídas publicadas:

- `data/output/sales_pipeline.duckdb`;
- `data/output/fact_sales_pipeline.parquet`;
- `data/output/quality_report.csv`;
- `data/quarantine/rejected_sales.csv`.

Tabelas DuckDB:

- `raw_vendas`;
- `dim_consultores`, `dim_lojas`, `dim_veiculos`;
- `fact_vendas`;
- `rejected_sales`;
- `quality_report`;
- `mart_vendas_mensal`.

Campos monetários da fato e do Parquet usam `DECIMAL(18,2)`; percentuais persistidos usam `DECIMAL(9,4)`. Entradas monetárias com mais de duas casas decimais não são arredondadas silenciosamente: são classificadas como inválidas.

## Camada analítica

Depois das validações, somente as vendas aprovadas formam `fact_vendas`. A fato
mantém os identificadores de venda, veículo, loja e consultor; data da venda;
atributos de loja (`loja`, `cidade`, `uf`), consultor e veículo (`marca`, `modelo`);
valores de referência e venda; descontos derivados; campos de qualidade e origem.
Isso atende às análises do desafio sem introduzir outro modelo dimensional.

O fluxo permanece direto:

```text
vendas válidas → fact_vendas/Parquet → mart e KPIs → dashboard
```

| KPI | Fórmula | Origem | Ausência de dados |
| --- | --- | --- | --- |
| Faturamento | `SUM(valor_venda)` | `fact_vendas` | venda sem valor válido não entra na fato |
| Quantidade de vendas | `COUNT(*)` | `fact_vendas` | zero quando a fato ou o filtro está vazio |
| Ticket médio | `SUM(valor_venda) / COUNT(*)` | fato e mart | não calculado sem vendas |
| Desconto absoluto | `valor_referencia - valor_venda` | `fact_vendas.desconto_valor` | nulo sem valor de referência; o agregado soma valores aplicáveis |
| Desconto ponderado | `SUM(desconto_valor) / SUM(valor_referencia) * 100` | mart e dashboard | exclui referência nula ou zero; fica nulo no mart e `N/D` no dashboard sem base aplicável |

O desconto ponderado usa o mesmo conjunto de linhas no numerador e denominador;
não é a média simples dos percentuais de cada venda. O indicador operacional de
aprovação exibido no dashboard continua sendo `vendas válidas / vendas recebidas`.

`mart_vendas_mensal` agrega a fato por mês, marca, loja e UF. Ele contém quantidade,
receita, ticket médio, desconto total e desconto percentual ponderado, preservando
`DECIMAL` nas métricas financeiras. O dashboard consulta a fato para permitir os
mesmos cálculos após filtros interativos; o Parquet materializa a mesma fato do
DuckDB.

## Regras de qualidade

O catálogo possui 18 regras: 12 `error` e 6 `warning`. Cada entrada de
`build_pipeline.QUALITY_RULES` declara `rule_id`, descrição, dataset, severidade,
condição, tratamento, justificativa e se invalida uma venda. Esses mesmos campos
compõem o `quality_report`.

- Em `vendas`, `error` significa que a linha não é confiável para a fato. A regra
  marca `invalidates_sale=true`, registra o `rule_id` em `quality_issues` e envia a
  linha à quarentena.
- Em dimensões, `error` qualifica as ocorrências duplicadas da origem. Elas não são
  carregadas em conjunto: somente a ocorrência canônica segue para os joins, sem
  invalidar automaticamente vendas que apontam para esse ID.
- `warning` registra uma anomalia relevante em `quality_issues`, mas preserva a
  venda na fato. Não há correção automática do valor suspeito.

As regras são avaliadas de forma independente sobre os dados normalizados. Assim,
uma linha pode conter vários `rule_id` separados por `|`, e o `failed_rows` de cada
regra inclui todas as linhas afetadas, mesmo quando elas também são rejeitadas por
outra regra.

| Regra | Severidade | Tratamento | Ocorrências na validação da Fase 2A |
| --- | --- | --- | ---: |
| `duplicate_consultor_id` | error | manter primeiro cadastro | 0 |
| `duplicate_loja_id` | error | manter primeiro cadastro | 0 |
| `duplicate_veiculo_id` | error | manter primeiro cadastro | 0 |
| `missing_venda_id` | error | rejeitar venda | 0 |
| `duplicate_venda_id` | error | manter primeira venda e rejeitar posteriores | 174 |
| `invalid_data_venda` | error | rejeitar venda | 69 |
| `future_data_venda` | warning | manter com aviso | 0 |
| `invalid_valor_venda` | error | rejeitar venda | 289 |
| `negative_valor_venda` | error | rejeitar venda | 35 |
| `invalid_valor_referencia` | warning | manter com aviso | 0 |
| `missing_veiculo_id` | error | rejeitar venda | 0 |
| `orphan_veiculo_id` | error | rejeitar venda | 58 |
| `missing_loja_id` | error | rejeitar venda | 0 |
| `orphan_loja_id` | error | rejeitar venda | 58 |
| `missing_consultor_id` | warning | manter com aviso | 0 |
| `orphan_consultor_id` | warning | manter com aviso | 117 |
| `consultor_loja_mismatch` | warning | manter com aviso | 58 |
| `veiculo_multiple_sales` | warning | manter com aviso | 406 |

### Política de duplicatas

A ordem consolidada é determinística: os arquivos ingeridos são ordenados pelo
nome de origem, e a ordem das linhas de cada CSV é preservada. A primeira
ocorrência nessa sequência é a ocorrência canônica.

| Chave | Ocorrência canônica | Demais ocorrências | Contagem no relatório |
| --- | --- | --- | --- |
| `venda_id` | permanece candidata à fato | rejeitadas como `duplicate_venda_id` | somente ocorrências posteriores |
| `consultor_id` | compõe `dim_consultores` | não entram na dimensão | todas as ocorrências do ID duplicado |
| `loja_id` | compõe `dim_lojas` | não entram na dimensão | todas as ocorrências do ID duplicado |
| `veiculo_id` | compõe `dim_veiculos` | não entram na dimensão | todas as ocorrências do ID duplicado |

As regras continuam independentes: a ocorrência canônica de uma venda ainda pode
ser rejeitada se falhar em outro `error`.

### Integridade referencial e quarentena

| Relação | Falha | Decisão | Fato e relatório |
| --- | --- | --- | --- |
| venda → veículo | ID ausente ou órfão | `error` | rejeita; registra a regra no `quality_report` e em `quality_issues` |
| venda → loja | ID ausente ou órfão | `error` | rejeita; registra a regra no `quality_report` e em `quality_issues` |
| venda → consultor | ID ausente ou órfão | `warning` | mantém a venda; atributos não resolvidos ficam nulos e a regra é registrada |
| consultor → loja da venda | lojas divergentes para consultor conhecido | `warning` | mantém a venda como possível operação cruzada e registra `consultor_loja_mismatch` |

`data/quarantine/rejected_sales.csv` recebe a linha quando ao menos um `error` de
`vendas` a invalida. Duplicatas de dimensão aparecem no relatório, mas não enviam
por si sós uma venda à quarentena.

### Limitações das regras

- `veiculo_multiple_sales` não prova duplicidade nem fraude; pode representar
  revenda ou recorrência e, sem contexto adicional, permanece `warning`.
- `consultor_loja_mismatch` pode representar venda cruzada legítima; não há base de
  negócio para rejeitar ou corrigir a loja.
- Uma venda com consultor ausente ou órfão ainda conserva veículo, loja e valor;
  por isso permanece utilizável com `warning`.
- O vínculo `consultor → loja` não possui uma regra independente para loja ausente
  no cadastro do consultor. O catálogo atual somente compara a loja conhecida do
  consultor com a loja da venda; ampliar essa política exige requisito de negócio.
- A seleção canônica de duplicatas não tenta reconciliar campos conflitantes: ela
  preserva a primeira ocorrência rastreável e expõe todas as duplicatas no relatório.

## Resultado controlado da Fase 2A

Execução em Python 3.14.5, com o ZIP original somente leitura e destinos temporários externos:

| Métrica | Antes do hardening | Depois |
| --- | ---: | ---: |
| Vendas recebidas | 115.879 | 115.879 |
| Vendas válidas | 115.128 | 115.198 |
| Vendas rejeitadas | 751 | 681 |
| Datas classificadas como inválidas | 140 | 69 |
| Faturamento válido | R$ 32.965.765.256,00 | R$ 32.987.527.556,00 |
| Desconto em valor | R$ 76.800.244,00 | R$ 77.090.644,00 |
| Ticket médio | R$ 286.340,1193 | R$ 286.355,0370 |

Das 71 datas válidas em formatos alternativos, 70 vendas foram recuperadas; uma delas também falha em outra regra crítica. Datas semanticamente impossíveis continuam rejeitadas.

## Dashboard e exportação

Execute o dashboard atual, preservado em Streamlit:

```powershell
.\.venv\Scripts\python.exe -m streamlit run dashboard.py
```

Ele lê `data/output/sales_pipeline.duckdb` em modo somente leitura. Para testes ou outro banco local:

```powershell
$env:SALES_PIPELINE_DB_PATH = "C:\caminho\sales_pipeline.duckdb"
.\.venv\Scripts\python.exe -m streamlit run dashboard.py
```

Uma `fact_vendas` vazia mostra uma mensagem controlada antes de construir o filtro de datas.

Exportação completa da fato para CSV, sem efeitos colaterais no import:

```powershell
.\.venv\Scripts\python.exe export_csv.py
```

## Verificações

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m pip_audit -r requirements.txt
git diff --check
```

Os testes usam somente fixtures artificiais e diretórios temporários. O ZIP e os outputs locais existentes não são usados como alvos destrutivos.

## Ferramentas de terceiros

| Ferramenta | Uso atual |
| --- | --- |
| Python 3.14.5 | Runtime e biblioteca padrão compatível com Windows. |
| Pandas | Limpeza, normalização, validações, joins e DataFrames. |
| NumPy | Composição vetorizada de marcações de qualidade. |
| DuckDB | Persistência e consultas analíticas locais; geração do Parquet e CSV. |
| Streamlit | Dashboard local existente. |
| Plotly | Gráficos interativos do dashboard. |
| NiceGUI | Dependência requerida na fundação; não substitui o dashboard Streamlit herdado nesta fase. |
| Pytest | Caracterização, regressão e testes funcionais. |
| Ruff | Lint e verificação de formatação. |
| pip-audit | Consulta de vulnerabilidades conhecidas nas dependências. |

## Uso de inteligência artificial

- **Ferramenta:** OpenAI Codex.
- **Uso:** análise do desafio e da auditoria, criação dos testes de caracterização, implementação incremental do hardening, revisão de segurança e atualização documental.
- **Controles:** mudanças divididas em commits recuperáveis; regras e métricas verificadas por testes e execuções locais; diff revisado antes de cada commit.
- **Dados:** nenhum arquivo do desafio foi enviado a serviço externo por esta implementação; a análise e os testes ocorreram no workspace local.

Decisões produzidas com IA devem ser revisadas pelo responsável antes da submissão final.

## Limitações atuais

- O hash físico do arquivo DuckDB pode mudar entre execuções, embora tabelas, contagens, agregações e demais artefatos permaneçam logicamente idempotentes.
- A publicação restaura os arquivos anteriores em falhas capturadas durante a substituição; encerramento abrupto do processo ou perda de energia entre substituições ainda pode exigir recuperação pelos arquivos `.bak`.
- Regras como venda anterior à admissão, quilometragem anômala e padronização semântica de marcas foram observadas, mas não foram adicionadas silenciosamente ao catálogo.
- NiceGUI permanece como dependência original; a interface funcional atual é Streamlit e não foi redesenhada nesta fase.
