# Automated Sales Pipeline

Pipeline local e reproduzível para receber arquivos comerciais, validar sua estrutura, tratar problemas de qualidade, consolidar vendas e disponibilizar dados confiáveis para análise. A solução preserva a origem, separa registros rejeitados em quarentena e publica uma camada analítica em DuckDB e Parquet. A execução e o dashboard funcionam localmente no Windows, sem servidor de banco de dados ou infraestrutura em nuvem.

## Visão geral da solução

```text
Arquivos de entrada
        ↓
Ingestão segura
        ↓
Validação estrutural e normalização
        ↓
Regras de qualidade
        ↓
Vendas válidas + quarentena/avisos
        ↓
Relacionamento com lojas, veículos e consultores
        ↓
Camada analítica
        ↓
DuckDB + Parquet
        ↓
Dashboard Streamlit / exportação CSV
```

Git, testes automatizados, rastreabilidade, documentação e práticas de DevOps/DevSecOps acompanham todo o fluxo. A linha de raciocínio foi preservar e compreender os dados antes de transformá-los: **entender → implementar → testar → observar → corrigir → versionar → avançar**.

## Início rápido

As instruções abaixo usam Windows e PowerShell. Não é necessário ativar manualmente o ambiente virtual porque os comandos chamam diretamente o Python da `.venv`.

### 1. Clonar e entrar no projeto

```powershell
git clone <URL-do-repositorio>
cd automated-sales-pipeline-final
```

### 2. Criar o ambiente virtual

```powershell
python -m venv .venv
```

### 3. Instalar as dependências

```powershell
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### 4. Colocar a entrada no projeto

Copie o ZIP recebido para:

```text
data/incoming/
```

### 5. Executar pipeline e dashboard

O launcher é a forma mais simples de executar a solução. Informe o nome do ZIP quando houver mais de um arquivo em `data/incoming/`:

```powershell
.\.venv\Scripts\python.exe app.py --zip "teste_candidatos.zip"
```

O `app.py` executa o pipeline e só abre o dashboard se o processamento terminar com sucesso. Com um único ZIP na pasta, também é possível executar:

```powershell
.\.venv\Scripts\python.exe app.py
```

Com zero ZIPs o launcher informa erro; com mais de um, exige `--zip` para não escolher uma entrada silenciosamente. Para listar as opções disponíveis:

```powershell
.\.venv\Scripts\python.exe app.py --list
```

### 6. Executar os componentes separadamente

Pipeline:

```powershell
.\.venv\Scripts\python.exe build_pipeline.py "data/incoming/teste_candidatos.zip" --output "data/output" --quarantine "data/quarantine"
```

Dashboard, após a criação do banco:

```powershell
.\.venv\Scripts\python.exe -m streamlit run dashboard.py
```

Exportação opcional da fato completa para CSV:

```powershell
.\.venv\Scripts\python.exe export_csv.py
```

### 7. Verificar o projeto

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

A suíte usa dados temporários próprios e não depende do ZIP oficial.

## Pré-requisitos

- Windows com PowerShell;
- Python compatível com as versões fixadas em `requirements.txt`;
- espaço local para o ambiente e os artefatos gerados.

O projeto foi desenvolvido e validado com **Python 3.14.5**. Essa é a versão de referência usada na entrega, não uma regra de negócio do pipeline.

## Como o desafio foi atendido

| Objetivo do desafio | Implementação |
|---|---|
| Receber | `pipeline.py` aceita ZIP, diretório ou CSV para ingestão e inspeção. |
| Compreender | Quatro schemas explícitos identificam vendas, lojas, veículos e consultores. |
| Validar | Estrutura, tipos e 20 regras de qualidade são avaliados antes da publicação. |
| Tratar | Textos, IDs, datas, números e dinheiro são normalizados por regras explícitas. |
| Consolidar | Vendas aprovadas são relacionadas às dimensões em `fact_vendas`. |
| Disponibilizar | DuckDB, Parquet, relatórios, dashboard e CSV opcional atendem usos analíticos. |
| Executar novamente | A mesma entrada reconstrói logicamente os outputs; novos lotes percorrem o mesmo fluxo. |

## Entrada dos dados

O pacote completo deve reunir os quatro conjuntos abaixo:

| Conteúdo | Caminho esperado no pacote |
|---|---|
| Consultores | `dados/dimensoes/dim_consultores.csv` |
| Lojas | `dados/dimensoes/dim_lojas.csv` |
| Veículos | `dados/dimensoes/dim_veiculos.csv` |
| Vendas | `dados/vendas/vendas_*.csv` |

Os CSVs usam `;`, UTF-8 ou UTF-8 com BOM e cabeçalhos exatos. A ingestão isolada consegue inspecionar um único CSV, mas o build completo precisa dos quatro schemas para construir os relacionamentos.

A entrada original é aberta somente para leitura. Seu conteúdo em bytes e seu tamanho são preservados; metadados controlados pelo sistema operacional, como horário de acesso, não são garantidos pela aplicação. Arquivos derivados são gravados apenas em `data/output/` e `data/quarantine/`.

## Saídas geradas

| Artefato | Finalidade |
|---|---|
| `data/output/sales_pipeline.duckdb` | Banco analítico local com dados brutos, dimensões, fato, rejeições, qualidade e mart mensal. |
| `data/output/fact_sales_pipeline.parquet` | Cópia colunar e portátil da `fact_vendas`, comprimida com ZSTD. |
| `data/output/quality_report.csv` | Resultado das regras, com severidade, tratamento, justificativa, ocorrências e status. |
| `data/quarantine/rejected_sales.csv` | Vendas rejeitadas, mantidas com motivos e origem para investigação. |
| `data/output/fact_sales_pipeline.csv` | Exportação opcional da fato completa, criada por `export_csv.py`. |

O DuckDB contém as tabelas `raw_vendas`, `dim_consultores`, `dim_lojas`, `dim_veiculos`, `fact_vendas`, `rejected_sales`, `quality_report` e `mart_vendas_mensal`.

Os artefatos gerados não são versionados. Eles podem ser reconstruídos a partir da entrada e dos comandos documentados.

## Arquitetura e responsabilidades

| Arquivo | Responsabilidade |
|---|---|
| `app.py` | Seleciona explicitamente o ZIP, executa o build com o mesmo Python da sessão e abre o dashboard após sucesso. |
| `pipeline.py` | Protege a fronteira de entrada, descobre arquivos, valida ZIP/CSV/schema e adiciona arquivo e linha de origem. |
| `build_pipeline.py` | Combina, normaliza, aplica qualidade, relaciona dimensões, calcula métricas e publica os artefatos. |
| `dashboard.py` | Consulta o DuckDB em modo somente leitura e apresenta KPIs, filtros, gráficos, qualidade e rastreabilidade. |
| `export_csv.py` | Exporta a `fact_vendas` completa para CSV, também por conexão somente leitura. |
| `tests/` | Exercita launcher, ingestão, regras, cálculos, persistência, dashboard, exportação e reexecução. |
| `SECURITY.md` | Registra limites de confiança, controles implementados e riscos residuais. |
| `docs/challenge.md` | Preserva o escopo funcional e os critérios de entrega do desafio. |

`pipeline.py` e `build_pipeline.py` permanecem separados intencionalmente: o primeiro valida a entrada não confiável; o segundo contém decisões de transformação e negócio.

## Estrutura do projeto

```text
automated-sales-pipeline-final/
├── .streamlit/config.toml
├── data/
│   ├── incoming/       # ZIPs locais de entrada (ignorados pelo Git)
│   ├── output/         # DuckDB, Parquet e relatório gerados
│   └── quarantine/     # vendas rejeitadas pelo pipeline
├── docs/challenge.md
├── tests/
├── app.py              # launcher: pipeline + dashboard
├── build_pipeline.py   # transformação, qualidade e publicação
├── dashboard.py        # dashboard Streamlit somente leitura
├── export_csv.py       # exportação opcional da fato completa
├── pipeline.py         # ingestão e validação estrutural
├── README.md
├── requirements.txt
└── SECURITY.md
```

## Principais decisões técnicas

| Tecnologia ou prática | Por que foi escolhida |
|---|---|
| Python | Automatiza todo o fluxo com uma base de código local, legível e fácil de executar no Windows. |
| Pandas | Mantém transformações tabulares e regras de qualidade explícitas e testáveis. |
| NumPy | Apoia a composição vetorizada das marcações de qualidade, sem processamento linha a linha. |
| DuckDB | Oferece SQL analítico e tipos decimais em um único arquivo, sem servidor externo. |
| Parquet | Fornece uma saída colunar compacta, portátil e adequada para consumo analítico. |
| Streamlit | Entrega uma interface local funcional sem exigir frontend, API ou implantação separada. |
| Plotly | Produz gráficos interativos compatíveis com os filtros do dashboard. |
| Pytest | Transforma regras e comportamentos esperados em verificações automatizadas. |
| Ruff | Verifica erros estáticos, estilo e formatação do código. |
| pip-audit | Consulta vulnerabilidades conhecidas nas dependências Python. |
| Git | Registra mudanças e checkpoints de forma incremental e revisável. |

### Por que a solução é local

Para o volume e o objetivo do desafio, AWS, GCP, Vercel, n8n, Make, banco remoto, Docker ou um orquestrador distribuído aumentariam configuração, custo, dependências e dificuldade de reprodução sem benefício proporcional. DuckDB, Parquet e Streamlit atendem ao caso com menos partes móveis e sem credenciais.

O runtime não usa cloud, API externa, banco remoto, autenticação ou MCP. As ferramentas de IA descritas adiante participaram do desenvolvimento, não da execução do pipeline.

## Qualidade dos dados

O tratamento separa ocorrência, severidade e destino:

- `error` em uma regra de venda que invalida o registro envia a linha para a quarentena;
- `error` em duplicidade de dimensão qualifica o conjunto e usa a primeira ocorrência como referência, mas não rejeita automaticamente uma venda;
- `warning` mantém a venda válida e registra a anomalia para análise;
- `quality_issues` guarda todos os identificadores aplicáveis à linha, pois uma venda pode falhar em mais de uma regra;
- a quarentena preserva os registros rejeitados em vez de apagá-los.

### Principais ocorrências na base de referência

| Regra | Severidade | Ocorrências | Tratamento principal |
|---|---:|---:|---|
| `duplicate_venda_id` | error | 174 | Mantém a primeira venda e envia posteriores à quarentena. |
| `invalid_data_venda` | error | 69 | Quarentena. |
| `invalid_valor_venda` | error | 289 | Quarentena. |
| `negative_valor_venda` | error | 35 | Quarentena. |
| `zero_valor_venda` | error | 34 | Quarentena. |
| `suspicious_valor_venda_placeholder` | error | 44 | Quarentena para o sentinel específico da fonte. |
| `orphan_veiculo_id` | error | 58 | Quarentena. |
| `orphan_loja_id` | error | 58 | Quarentena. |
| `orphan_consultor_id` | warning | 117 | Mantém a venda e sinaliza. |
| `consultor_loja_mismatch` | warning | 58 | Mantém a venda e sinaliza. |
| `veiculo_multiple_sales` | warning | 406 | Mantém as vendas e sinaliza. |

O catálogo completo possui **20 regras: 14 `error` e 6 `warning`** e está disponível em `quality_report`. A tabela acima destaca apenas regras com ocorrências na base fornecida. As ocorrências podem se sobrepor na mesma linha; por isso a soma de `failed_rows` não equivale ao total de vendas rejeitadas.

### Tratamentos que exigiram decisão explícita

- Datas são aceitas somente nos formatos conhecidos `AAAA-MM-DD`, `AAAA/MM/DD` e `DD/MM/AAAA`; datas impossíveis não são corrigidas por adivinhação.
- Dinheiro é processado com `Decimal` no Python e `DECIMAL` no DuckDB/Parquet para preservar centavos.
- `valor_venda = 0` é rejeitado porque não representa uma venda comercial válida para os KPIs deste desafio.
- `valor_venda = 9.999.999` é tratado como sentinel/placeholder desta fonte após a análise da distribuição e das referências. Essa regra deve ser revista se a origem mudar.
- Duplicatas seguem ordem determinística: arquivos por nome e linhas pela posição física; a primeira ocorrência é a referência.

### Métricas financeiras

```text
faturamento = soma(valor_venda)
ticket médio = faturamento / quantidade de vendas válidas
desconto concedido = max(valor_referencia - valor_venda, 0)
ágio sobre a referência = max(valor_venda - valor_referencia, 0)
variação líquida = desconto concedido - ágio
```

O desconto ponderado considera apenas vendas efetivamente abaixo da referência, tanto no numerador quanto no denominador. Desconto e ágio permanecem separados para que uma venda acima da referência não esconda desconto concedido em outra.

## Resultado de referência

Valores confirmados em modo somente leitura nos artefatos existentes para `teste_candidatos.zip`, cujo SHA-256 é `06BE13B4E818849568965B0E3E7BA64F9EDC78BE8D8207C9A088C35773D60DAD`:

| Métrica | Resultado |
|---|---:|
| Vendas recebidas | 115.879 |
| Vendas válidas | 115.121 |
| Vendas rejeitadas | 758 |
| Taxa de aprovação | 99,35% |
| Faturamento | R$ 32.547.527.600,00 |
| Ticket médio | R$ 282.724,50 |
| Desconto concedido | R$ 751.462.600,00 |
| Ágio sobre a referência | R$ 253.100.900,00 |
| Variação líquida | R$ 498.361.700,00 |
| Desconto ponderado | 3,4145% |

As contagens e somas da fato foram comparadas logicamente entre DuckDB, Parquet e `mart_vendas_mensal`. Esses números pertencem à base fornecida; não são constantes fixas no sistema.

## Dashboard

O dashboard é uma camada de consulta: ele não executa nem altera o processamento. `dashboard.py` abre `sales_pipeline.duckdb` com `read_only=True` e oferece:

- KPIs de faturamento, vendas, ticket médio e desconto concedido;
- filtros por período, marca, loja, UF, canal, forma de pagamento e consultor;
- gráficos de evolução mensal, marca, loja, canal e forma de pagamento;
- tema claro e escuro;
- aba de qualidade com volumes, taxa de aprovação, regras, filtros locais e download do relatório;
- aba de rastreabilidade com busca, filtro de alertas, ordenação, arquivo/linha de origem e download dos dados investigados.

O download do dashboard respeita a investigação atual. Já `export_csv.py` exporta a fato completa, sem filtros, para uso automatizável fora da interface.

## Rastreabilidade

Cada linha recebe os campos:

- `__source_file`: arquivo de origem;
- `__source_line`: linha física em que o registro começou;
- `quality_issues`: regras de qualidade associadas.

Esses campos seguem para a fato ou para a quarentena. Assim, se um número da camada analítica for questionado, é possível localizar a entrada correspondente e entender quais validações foram aplicadas. O arquivo original permanece preservado e os rejeitados continuam disponíveis para investigação.

## Reexecução e reprodutibilidade

Quando um novo pacote for recebido:

1. coloque o ZIP em `data/incoming/`;
2. execute `app.py --zip "<arquivo>.zip"`;
3. o pipeline valida novamente a entrada e todas as regras;
4. a camada analítica é reconstruída e publicada nos destinos documentados;
5. o dashboard consulta o banco atualizado.

Os testes comprovam **idempotência lógica** para a mesma entrada: contagens, schemas e métricas são reproduzidos. O hash físico do arquivo DuckDB não é usado como critério, pois detalhes internos do banco podem variar sem alterar seu conteúdo lógico.

## Segurança e robustez da ingestão

A entrada é tratada como não confiável antes de chegar às regras de negócio. Entre os controles implementados estão allowlist de caminhos, bloqueio de ZIP Slip, links e tipos especiais, validação de CRC, limites de arquivos/tamanho/compressão, UTF-8 estrito, delimitador e schema exatos. A publicação usa staging no mesmo volume e tenta restaurar o conjunto anterior quando uma substituição falha com erro capturado.

O modelo de ameaça, os limites exatos e os riscos residuais estão em [`SECURITY.md`](SECURITY.md).

## Testes e verificações

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m pip_audit -r requirements.txt
git diff --check
```

- Pytest verifica os contratos funcionais e de integração.
- Ruff verifica problemas estáticos e formatação.
- `pip check` detecta incompatibilidades entre pacotes instalados.
- `pip-audit` consulta vulnerabilidades conhecidas nas dependências.
- `git diff --check` detecta erros de whitespace no diff.

Na revisão desta entrega, a suíte atual executou **117 testes com sucesso**.

## Metodologia de desenvolvimento

O projeto usou como referência uma adaptação do ciclo DevOps/DevSecOps apresentado pela IBM; não é um projeto IBM, não utiliza infraestrutura IBM e não aplica um framework proprietário integralmente.

O ciclo **Planejar → Programar → Construir → Testar → Lançar → Implementar → Operar → Monitorar** foi traduzido para o contexto do desafio como: planejar uma pequena evolução, implementar, testar, analisar os resultados, corrigir, versionar e avançar. Segurança foi incorporada desde a ingestão por meio da preservação da origem, validação antecipada, testes, Ruff, `pip-audit`, rastreabilidade e consumidores do banco em modo somente leitura.

Referências metodológicas:

- [IBM — Ciclo de vida de DevOps](https://www.ibm.com/br-pt/think/topics/devops-lifecycle)
- [IBM — DevSecOps](https://www.ibm.com/br-pt/think/topics/devsecops)

## Uso de Inteligência Artificial

### OpenAI Codex no VS Code

Foi utilizado como apoio à implementação incremental, leitura e revisão de código, refatorações delimitadas, criação de testes e execução de verificações no workspace.

### ChatGPT

Foi utilizado como apoio à análise do desafio, discussão da arquitetura, investigação de problemas, revisão de decisões e estruturação da documentação.

As sugestões não foram tratadas como fonte de verdade. O fluxo adotado foi:

```text
problema → proposta da IA → revisão humana → execução → comparação com os dados → ajuste
```

Código e decisões apoiados por IA foram verificados por leitura, execução local, testes automatizados, inspeção das saídas, comparação das métricas, relatório de qualidade e histórico Git. A implementação não chama serviços de IA em runtime nem envia os dados do pipeline a esses serviços.

**A IA foi utilizada como ferramenta de apoio; a responsabilidade e a validação da solução permaneceram com o desenvolvedor.**

## Git e desenvolvimento incremental

Git foi usado para versionamento, revisão de diferenças e registro dos marcos do projeto. O desenvolvimento avançou em pequenos incrementos conceituais: fundação → ingestão → qualidade → consolidação → análise → dashboard → testes e documentação. O histórico preserva essas decisões sem ser necessário conhecer os nomes internos das fases para executar o produto final.

## Limitações e fronteiras da solução

- O contrato é específico aos quatro schemas conhecidos; alterações de origem exigem evolução explícita do contrato.
- O build completo precisa de vendas e das três dimensões no mesmo conjunto de entrada.
- O processamento e a carga do dashboard ocorrem em memória, adequados ao volume atual, mas não a volumes distribuídos.
- A execução é local, de um lote por vez, sem lock para concorrência ou orquestração de múltiplos produtores.
- A publicação reduz o risco de conjunto parcial e possui rollback para falhas capturadas, mas não é uma transação multi-arquivo resistente a toda interrupção abrupta.
- A regra de data futura depende do relógio local, e o sentinel `9.999.999` é uma decisão específica desta fonte.
- O dashboard não possui autenticação e foi projetado para uso local, não para exposição direta em rede não confiável.
- As versões diretas estão fixadas, mas não há lockfile com hashes de todas as dependências transitivas.

Essas fronteiras mantêm a entrega proporcional ao desafio. Evoluções como processamento incremental, autenticação, cloud ou execução distribuída só devem ser introduzidas diante de requisitos reais de volume, concorrência, disponibilidade ou segurança operacional.

## Reprodução rápida

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe app.py --zip "teste_candidatos.zip"
```
