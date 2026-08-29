# Política de Segurança

## Escopo

Esta política cobre `pipeline.py`, seus testes e a execução local da CLI de inspeção. Nesta fase, não há interface, banco, serviço de rede, autenticação, cloud ou persistência analítica.

A única superfície de entrada implementada é um caminho local informado pelo usuário para um ZIP, um CSV ou um diretório. Todo conteúdo recebido é tratado como não confiável, inclusive o pacote do desafio.

## Ativos e limites de confiança

Devem ser preservados:

- o conteúdo em bytes e o tamanho dos arquivos originais; metadados controlados pelo sistema operacional, como horário de acesso, não são garantidos pela aplicação;
- a confidencialidade e a integridade dos demais arquivos do host;
- a disponibilidade do processo local diante de entradas malformadas;
- a rastreabilidade de cada linha carregada até o arquivo e a linha física de origem.

O arquivo ou diretório informado e todo membro de ZIP são não confiáveis. O sistema operacional local, o interpretador Python, as dependências instaladas e o usuário que inicia o processo ficam fora desse limite e são considerados confiáveis. A aplicação não confia em identidade externa e não faz acesso de rede.

## Invariantes de segurança

- Entradas originais são abertas somente para leitura e nunca são movidas, renomeadas ou sobrescritas.
- Nenhum membro de ZIP pode escapar do diretório temporário de extração.
- Links simbólicos, junctions do Windows, caminhos absolutos, UNC, drives, `.` e `..` são rejeitados nos pontos aplicáveis.
- Todo o ZIP é inspecionado, limitado e verificado por CRC antes da extração temporária.
- Diretórios são descobertos sem seguir links e cada caminho resolvido deve permanecer sob a raiz informada.
- CSVs só são aceitos em UTF-8, com ou sem BOM, delimitador `;` e schema exato conhecido.
- Valores de domínio permanecem texto; a ingestão não corrige, converte, deduplica nem descarta linhas.
- Erros esperados falham de forma fechada, com mensagem clara e código de saída não zero.

## Validação de ZIP

A allowlist aceita somente o `README.md` opcional na raiz, os três nomes conhecidos em `dados/dimensoes/` e lotes de vendas compatíveis com o padrão conhecido em `dados/vendas/`. Qualquer outro conteúdo invalida o arquivo inteiro.

Também são rejeitados membros criptografados, métodos diferentes de `stored` e `deflated`, links, arquivos especiais, tipos Unix incoerentes, colisões de caminho sem distinção entre maiúsculas e minúsculas e falhas de CRC ou DEFLATE.

| Controle | Limite |
| --- | ---: |
| Tamanho do ZIP compactado | 64 MiB |
| Arquivos regulares no ZIP ou diretório | 32 |
| Tamanho declarado ou copiado por membro | 32 MiB |
| Total descompactado declarado | 64 MiB |
| Razão de compressão por membro | 200:1 |

Os limites são verificados antes e durante a cópia. Excedê-los invalida a entrada; eles não são truncamentos silenciosos.

## CSV, rastreabilidade e temporários

O parser usa UTF-8 estrito e rejeita BOM UTF-16/32, NUL, delimitador divergente, cabeçalhos ausentes, extras, duplicados ou reordenados e registros com largura incorreta. As colunas `__source_file` e `__source_line` são acrescentadas somente em memória.

ZIPs aprovados são extraídos com criação exclusiva (`xb`) em um `TemporaryDirectory` do sistema operacional. Apenas membros previamente validados são copiados, e o diretório temporário é removido ao sair do contexto, tanto em sucesso quanto em falha esperada. Nada é extraído para o repositório e nenhum arquivo DuckDB, Parquet ou de saída é criado nesta fase.

## Achados reportáveis e severidade

São achados de segurança, entre outros:

- escrita, sobrescrita ou execução fora do diretório temporário, ou alteração da entrada original: alta ou crítica conforme o impacto;
- leitura fora da raiz indicada por meio de link, junction ou desvio de caminho: alta quando expõe arquivo arbitrário;
- bypass reproduzível dos limites com exaustão relevante de memória, CPU ou disco: média ou alta conforme custo e impacto;
- entrada malformada que cause traceback não controlado, vazamento de temporário ou negação de serviço limitada: baixa ou média conforme a explorabilidade.

A severidade deve considerar pré-requisitos locais, controle necessário sobre a entrada, repetibilidade e impacto real. Anomalias comerciais — datas, valores, duplicatas, órfãos ou campos vazios — não são vulnerabilidades por si só.

## Limitações e riscos residuais

- CRC detecta corrupção acidental, mas não autentica a origem do pacote nem substitui assinatura digital.
- Não há antivírus ou análise de malware; a allowlist apenas reduz os tipos de conteúdo aceitos.
- Pandas pode consumir memória acima do tamanho bruto do CSV, ainda que os limites reduzam a exposição.
- Uma troca concorrente do arquivo entre validação e leitura permanece um risco local de tempo de verificação versus uso.
- A confidencialidade do temporário depende das permissões e da segurança do sistema operacional local.
- A cadeia de dependências é verificada com `pip-audit`, mas isso não elimina riscos de supply chain.

Não há exceções de segurança formalmente aceitas nesta fase.

## Como relatar

Relate vulnerabilidades em canal privado ao responsável pelo repositório ou pelo processo do desafio antes de divulgação pública. Inclua o commit afetado, impacto, pré-requisitos, passos de reprodução e, quando possível, um caso mínimo com dados artificiais. Não anexe os dados reais do desafio.

Esta política deve ser revista quando forem adicionados persistência, DuckDB, interface, exportações ou qualquer integração externa.
