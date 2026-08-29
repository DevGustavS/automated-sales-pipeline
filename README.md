# Automated Sales Pipeline

Fundação do repositório para o desafio técnico **Automated Sales Pipeline — 20260825**. O objetivo final é reduzir o trabalho manual de recebimento, tratamento, consolidação e disponibilização de dados comerciais fictícios de um grupo automotivo multimarcas.

> **Estado atual:** a Fase 1 implementa somente descoberta, leitura segura e validação estrutural. Regras de qualidade, transformações, DuckDB e interface NiceGUI continuam não implementados.

## Escopo desta entrega

Esta etapa adiciona uma CLI independente para inspecionar um ZIP, um CSV ou um diretório, validar o formato real e conferir os schemas conhecidos. Os arquivos fornecidos permanecem na raiz, exatamente onde foram recebidos:

- `Technical Challenge - Automated Sales Pipeline.md`;
- `Teste_Tecnico_Dados_Candidato_20260825.zip`.

Nenhum original é movido, renomeado, regravado ou duplicado. Para ZIPs aprovados, somente os CSVs permitidos são extraídos em um diretório temporário do sistema, carregados em memória e removidos automaticamente. Nenhum dado processado é gravado nesta fase. Também não foram adicionados cloud, Docker, banco externo, autenticação, MCP ou outros serviços externos.

## Mapeamento dos requisitos do desafio

Os arquivos podem estar incompletos, inconsistentes ou conter outros problemas de qualidade. Nesta fase, formatos e chaves candidatas foram observados e documentados; regras de tratamento, critérios de validade e o modelo analítico serão definidos somente em etapas futuras.

| Requisito final | Abordagem planejada | Situação atual |
| --- | --- | --- |
| 1. Receber os arquivos | Aceitar ZIP, CSV ou diretório local sem modificar as fontes. | Fase 1 concluída |
| 2. Compreender e relacionar as estruturas | Validar os quatro schemas reais e documentar chaves e relacionamentos aparentes. | Estrutura concluída; joins não implementados |
| 3. Identificar problemas de qualidade | Documentar observações; regras e quarentena serão definidas em fase posterior. | Apenas descoberta |
| 4. Realizar os tratamentos necessários | Aplicar transformações determinísticas e justificadas com Pandas. | Planejado |
| 5. Consolidar as informações | Consolidar localmente com Pandas e DuckDB, sem banco externo. | Planejado |
| 6. Gerar uma camada adequada para análise | Publicar dados tratados em `data/processed/`, com consultas locais no DuckDB e artefatos em `output/`. | Planejado |
| 7. Permitir novas execuções | Expor CLI determinística e cobrir a ingestão com Pytest. | Parcialmente concluído |
| Repositório organizado e documentado | Manter estrutura simples, dependências explícitas, decisões e instruções neste README. | Fundação criada |
| Ferramentas externas e IA documentadas | Registrar finalidade, forma de reprodução, uso de IA e validações realizadas. | Documentado abaixo |

## Estrutura

```text
.
├── data/
│   ├── incoming/      # entradas locais, preservadas sem alteração
│   ├── processed/     # dados gerados e aprovados
│   └── quarantine/    # dados gerados e rejeitados pelas validações
├── output/            # relatórios e exportações gerados
├── tests/             # testes artificiais da ingestão
├── .gitignore
├── AGENTS.md
├── README.md
├── SECURITY.md
├── pipeline.py
└── requirements.txt
```

Arquivos de dados dentro dessas áreas, resultados, temporários e bancos locais não são versionados; arquivos `.gitkeep` preservam somente os diretórios vazios no Git.

## Inspeção segura

Execute no PowerShell:

```powershell
.\.venv\Scripts\python.exe pipeline.py inspect "Teste_Tecnico_Dados_Candidato_20260825.zip"
```

A saída JSON apresenta somente valores calculados na execução: arquivo de origem, schema, encoding, delimitador, cabeçalhos e quantidade de linhas.

Entradas aceitas:

- arquivo `.zip` com ao menos um CSV nos caminhos permitidos em `dados/dimensoes/` ou `dados/vendas/`; o `README.md` de metadados na raiz é opcional;
- arquivo `.csv` em UTF-8, com ou sem BOM, delimitado por `;` e correspondente a um dos schemas conhecidos;
- diretório percorrido recursivamente e em ordem determinística, contendo CSVs conhecidos; o `README.md` da raiz e arquivos `.gitkeep` são ignorados.

O programa rejeita extensões, conteúdo ou schemas inesperados; ZIP inválido, criptografado ou com método de compressão não permitido; caminhos absolutos, UNC, com barra invertida, `.` ou `..`; links simbólicos, junctions do Windows e arquivos especiais; colisões de nomes no Windows; UTF-16/32, UTF-8 inválido, NUL, delimitador divergente e linhas com largura incorreta.

Limites atuais:

- ZIP compactado: 64 MiB;
- até 32 arquivos no ZIP e até 32 entradas, incluindo diretórios, na entrada por diretório;
- até 32 MiB por CSV ou membro;
- até 64 MiB descompactados no ZIP ou somados no diretório;
- razão máxima de compressão por membro: 200:1.

Códigos de saída: `0` para sucesso, `2` para entrada inválida, `3` para ZIP inválido ou inseguro e `4` para CSV, formato ou schema inválido. Falhas internas não esperadas não são ocultadas.

## Descoberta dos dados fornecidos

O ZIP foi inspecionado por streams, sem extração no repositório. Ele contém 11 arquivos regulares: 10 CSVs e um `README.md` de metadados. Todos os CSVs usam UTF-8 com BOM (`utf-8-sig`), delimitador `;`, cabeçalho na primeira linha e largura consistente. O README interno usa UTF-8 sem BOM.

| Arquivo no ZIP | Extensão | Compactado | Descompactado | Linhas de dados | Finalidade aparente |
| --- | --- | ---: | ---: | ---: | --- |
| `dados/dimensoes/dim_consultores.csv` | `.csv` | 693 B | 3.192 B | 64 | Cadastro de consultores e loja/equipe de vínculo. |
| `dados/dimensoes/dim_lojas.csv` | `.csv` | 158 B | 355 B | 8 | Cadastro de lojas e localização. |
| `dados/dimensoes/dim_veiculos.csv` | `.csv` | 1.322.991 B | 10.750.182 B | 120.000 | Cadastro e atributos dos veículos. |
| `dados/vendas/vendas_2024.csv` | `.csv` | 795.927 B | 3.803.892 B | 46.764 | Lote de vendas de 2024. |
| `dados/vendas/vendas_2025.csv` | `.csv` | 843.382 B | 4.048.589 B | 49.761 | Lote de vendas de 2025. |
| `dados/vendas/vendas_2026_01.csv` | `.csv` | 58.405 B | 279.063 B | 3.429 | Lote de vendas de janeiro de 2026. |
| `dados/vendas/vendas_2026_02.csv` | `.csv` | 57.018 B | 273.513 B | 3.358 | Lote de vendas de fevereiro de 2026. |
| `dados/vendas/vendas_2026_03.csv` | `.csv` | 72.356 B | 347.206 B | 4.270 | Lote de vendas de março de 2026. |
| `dados/vendas/vendas_2026_04.csv` | `.csv` | 67.745 B | 323.802 B | 3.977 | Lote de vendas de abril de 2026. |
| `dados/vendas/vendas_2026_05.csv` | `.csv` | 73.163 B | 351.395 B | 4.320 | Lote de vendas de maio de 2026. |
| `README.md` | `.md` | 417 B | 847 B | 30 linhas | Descrição da estrutura do pacote. |

Total calculado nos CSVs: 235.951 linhas, sendo 120.072 nas dimensões e 115.879 em vendas.

### Schemas encontrados

- **consultores:** `consultor_id`, `consultor`, `loja_id`, `equipe`, `data_admissao`;
- **lojas:** `loja_id`, `loja`, `cidade`, `uf`, `cluster`;
- **veículos:** `veiculo_id`, `ano_modelo`, `marca`, `modelo`, `versao`, `carroceria`, `cambio`, `combustivel`, `tipo_veiculo`, `quilometragem`, `cor_externa`, `cor_interna`, `score_avaliacao`;
- **vendas:** `venda_id`, `data_venda`, `veiculo_id`, `loja_id`, `consultor_id`, `canal_origem`, `forma_pagamento`, `valor_referencia`, `valor_venda`.

### Chaves e relacionamentos aparentes

- `dim_lojas.loja_id`, `dim_consultores.consultor_id` e `dim_veiculos.veiculo_id` são chaves candidatas completas e únicas: 8/8, 64/64 e 120.000/120.000;
- `vendas.loja_id` aparenta referenciar `dim_lojas.loja_id`;
- `vendas.consultor_id` aparenta referenciar `dim_consultores.consultor_id`;
- `vendas.veiculo_id` aparenta referenciar `dim_veiculos.veiculo_id`;
- `dim_consultores.loja_id` aparenta referenciar `dim_lojas.loja_id`;
- há 115.705 `venda_id` distintos nas 115.879 linhas de vendas.

Esses relacionamentos ainda não são executados como joins nem aplicados como regras.

### Formatos e valores inesperados observados

- 174 linhas excedentes de venda são duplicatas exatas;
- há referências órfãs `LOJ999` em 58 linhas, `CON999` em 117 e `VEI9999999` em 58;
- 71 datas válidas usam formatos alternativos (`YYYY/MM/DD` ou `DD/MM/YYYY`) e 69 datas são semanticamente inválidas;
- `valor_venda` possui 289 vazios, 35 valores `-5000`, 34 zeros e 44 valores `9999999`;
- em veículos, há 2.160 versões, 1.080 câmbios, 720 cores internas e 420 scores vazios;
- `marca` apresenta 28 grafias brutas para 7 marcas aparentes, incluindo variação de caixa, 272 espaços finais e `Leap Motor` versus `Leapmotor`;
- `quilometragem` possui 116 valores negativos e 124 valores acima de 200 mil;
- 26.319 vendas têm data anterior à admissão do consultor informado; dois consultores têm admissão posterior à data nominal do pacote;
- `score_avaliacao`, quando preenchido, usa vírgula decimal.

Esses números são resultados da descoberta, não regras implementadas. A definição de validade, severidade, correção e tratamento pertence a uma fase posterior.

### Comparação com o enunciado

O `README.md` interno do pacote descreve dimensões de apoio e vendas recebidas em lotes, uma organização compatível com o contexto comercial do enunciado. As inconsistências observadas confirmam a advertência do desafio de que os arquivos podem conter problemas de qualidade. Como o enunciado não prescreve regras, chaves ou tratamentos, esta fase adota a interpretação conservadora: valida somente contêiner, encoding, delimitador e schema, preservando todos os valores para análise futura.

## Limitações da Fase 1

Ainda não são executados regras de qualidade, limpeza, normalização, transformação, deduplicação, validação referencial, joins, persistência em DuckDB/Parquet, quarentena, indicadores, gráficos ou interface NiceGUI.

## Ambiente local no Windows

Pré-requisito: Python 3.14.5 disponível pelo comando `python`. No PowerShell, a partir da raiz do repositório:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Os comandos usam diretamente o Python do ambiente virtual e não dependem da política de execução necessária para ativar scripts no PowerShell.

Verificações do desenvolvimento:

```powershell
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pip_audit -r requirements.txt
```

Os testes usam somente fixtures pequenas e artificiais criadas em diretórios temporários; os dados reais não são copiados para `tests/`.

## Ferramentas de terceiros

Todas as dependências são instaladas localmente por `pip`, nas versões registradas em `requirements.txt`.

| Ferramenta | Uso previsto |
| --- | --- |
| Python | Linguagem e runtime do projeto. |
| Pandas | Armazenamento textual em memória após parsing e validação estrutural. |
| DuckDB | Consolidação e consultas analíticas em processo, com arquivo local ignorado pelo Git. |
| NiceGUI | Interface local futura; não implementada nesta etapa. |
| Pytest | Testes automatizados. |
| Ruff | Lint e verificação de formatação. |
| pip-audit | Auditoria das dependências Python em busca de vulnerabilidades conhecidas. |

Não há plataforma em nuvem nem serviço hospedado integrado ao projeto. A execução futura será local; uma conexão com a internet pode ser necessária somente para instalar pacotes pelo PyPI e consultar as bases de vulnerabilidades usadas pelo pip-audit.

## Uso de inteligência artificial

- **Ferramenta:** OpenAI Codex.
- **Atividades:** análise do enunciado, fundação, desenho da ingestão segura, testes artificiais e documentação das descobertas.
- **Verificação:** schemas, contagens e formatos foram recalculados a partir dos arquivos; ZIP Slip, limites, temporários, rastreabilidade e imutabilidade foram cobertos por testes. O responsável pela entrega deve revisar e validar as decisões antes da submissão final.

## Próximas etapas, fora desta entrega

1. definir, justificar e testar regras de qualidade com base nas descobertas;
2. decidir tratamentos, deduplicação e política de quarentena;
3. implementar relacionamentos e consolidação;
4. criar a camada analítica no DuckDB;
5. implementar a interface local com NiceGUI.
