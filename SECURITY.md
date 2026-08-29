# Política de Segurança

## Escopo

Esta política cobre a ingestão em `pipeline.py`, o tratamento e a persistência em `build_pipeline.py`, o dashboard local em `dashboard.py`, a exportação em `export_csv.py` e seus testes.

O sistema é local: não possui cloud, serviço de rede próprio, banco externo, autenticação ou MCP. O servidor iniciado pelo Streamlit é uma ferramenta local de visualização e deve permanecer restrito ao host, salvo decisão operacional explícita do usuário.

## Ativos e limites de confiança

Devem ser preservados:

- o conteúdo em bytes e o tamanho dos arquivos originais; metadados controlados pelo sistema operacional, como horário de acesso, não são garantidos pela aplicação;
- a confidencialidade e a integridade dos demais arquivos do host;
- a disponibilidade do processo diante de entradas malformadas;
- a rastreabilidade de cada linha até o arquivo e a linha física de origem;
- a consistência entre DuckDB, Parquet, relatório de qualidade e quarentena.

ZIPs, CSVs, diretórios de entrada e seus conteúdos são não confiáveis. Python, as dependências instaladas, o sistema operacional e o usuário que inicia a aplicação ficam fora desse limite. DuckDB e Parquet devem ser consumidos somente quando gerados pelo pipeline ou fornecidos por uma origem local confiável.

## Invariantes de ingestão

- Entradas originais são abertas somente para leitura e nunca são movidas, renomeadas ou sobrescritas.
- Nenhum membro de ZIP pode escapar do diretório temporário de extração.
- Links simbólicos, junctions do Windows, caminhos absolutos, UNC, drives, `.` e `..` são rejeitados nos pontos aplicáveis.
- O ZIP inteiro é inspecionado, limitado e verificado por CRC antes da extração temporária.
- Diretórios são descobertos sem seguir links; cada caminho resolvido deve permanecer sob a raiz informada.
- CSVs são aceitos somente em UTF-8, com ou sem BOM, delimitador `;` e schema exato conhecido.
- A ingestão preserva os valores como texto e acrescenta rastreabilidade somente em memória.
- Erros esperados falham de forma fechada, com mensagem clara e código de saída não zero.

## Controles de ZIP e CSV

A allowlist aceita o `README.md` opcional na raiz do ZIP, os três arquivos conhecidos em `dados/dimensoes/` e lotes compatíveis com o padrão conhecido em `dados/vendas/`. Conteúdo inesperado invalida o pacote.

Também são rejeitados membros criptografados, compressão diferente de `stored`/`deflated`, links, arquivos especiais, tipos Unix incoerentes, colisões de caminho sem distinção entre maiúsculas e minúsculas, falhas de CRC/DEFLATE, UTF-16/32, UTF-8 inválido, NUL, cabeçalhos divergentes e linhas com largura incorreta.

| Controle | Limite |
| --- | ---: |
| ZIP compactado | 64 MiB |
| Arquivos regulares no ZIP ou diretório | 32 |
| CSV ou membro individual | 32 MiB |
| Total descompactado ou somado | 64 MiB |
| Razão de compressão por membro | 200:1 |

Os limites são verificados antes e durante a cópia; não há truncamento silencioso.

## Tratamento, qualidade e rastreabilidade

Normalização e regras operam sobre cópias em memória. A origem textual dos campos de data e dinheiro é preservada em colunas `*_original`, enquanto `__source_file` e `__source_line` acompanham vendas, dimensões e fato.

O catálogo de qualidade é explícito. Regras que invalidam vendas são separadas de avisos; a linha rejeitada conserva todas as regras disparadas e vai para `data/quarantine/rejected_sales.csv` e para a tabela DuckDB `rejected_sales`. Novas regras não devem ser adicionadas sem justificativa, teste e documentação.

Valores monetários são analisados com `Decimal`; valores com mais de duas casas decimais são rejeitados em vez de arredondados silenciosamente. A persistência usa tipos `DECIMAL` com escala definida.

## Persistência e recuperação

DuckDB, Parquet, relatório e quarentena são construídos em staging no mesmo volume dos destinos. A publicação usa `os.replace`. Se uma substituição gera `OSError`, os arquivos já substituídos são removidos e seus backups são restaurados.

Esse mecanismo protege falhas capturadas durante a publicação, mas não equivale a uma transação distribuída entre diretórios. Encerramento abrupto do processo, falha do sistema operacional ou perda de energia entre substituições pode deixar arquivos `.bak` ou um conjunto parcial. Nessa situação:

1. interrompa leitores do DuckDB;
2. preserve os arquivos existentes e `.bak` antes de qualquer nova execução;
3. restaure o conjunto anterior ou execute novamente o pipeline com a mesma entrada validada;
4. confira contagens, relatório e hashes dos artefatos determinísticos.

O dashboard e o exportador abrem o DuckDB em modo somente leitura. Nomes de tabelas e consultas são constantes da aplicação; caminhos usados em `COPY` têm aspas simples escapadas. O caminho alternativo de banco via `SALES_PIPELINE_DB_PATH` é uma configuração local confiada ao usuário.

## Dependências e execução local

Dependências diretas são fixadas em `requirements.txt`, verificadas por `pip check` e auditadas com `pip-audit`. Isso reduz variação e identifica vulnerabilidades conhecidas, mas não elimina riscos de supply chain.

Use Python 3.14.5 e uma `.venv` criada por esse runtime. Não execute o pipeline com privilégios administrativos sem necessidade. Mantenha `data/incoming/`, `data/output/` e `data/quarantine/` acessíveis apenas aos usuários locais que precisam dos dados.

## Riscos residuais

- CRC detecta corrupção acidental, mas não autentica a origem do ZIP nem substitui assinatura digital.
- Não há antivírus ou análise de malware; a allowlist apenas reduz conteúdo aceito.
- Pandas pode consumir mais memória que o tamanho bruto dos CSVs.
- Uma troca concorrente do arquivo entre validação e leitura permanece um risco local de tempo de verificação versus uso.
- A confidencialidade dos temporários depende das permissões do sistema operacional.
- CSV exportado pode exigir cuidado ao ser aberto em planilhas que interpretem fórmulas; não trate exportações de origem desconhecida como conteúdo executável.
- O servidor Streamlit não adiciona autenticação; não o exponha em rede não confiável.
- O hash físico do DuckDB não é estável entre reexecuções, portanto a verificação deve usar schema, contagens e agregações lógicas.

## Como relatar

Relate vulnerabilidades em canal privado ao responsável pelo repositório antes de divulgação pública. Inclua commit afetado, impacto, pré-requisitos, passos de reprodução e um caso mínimo com dados artificiais. Não anexe os dados reais do desafio.
