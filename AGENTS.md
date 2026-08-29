# AGENTS.md

## Objetivo

Manter o pipeline local, simples, determinístico, auditável e compatível com Windows. Preserve a arquitetura atual em Pandas, DuckDB e Streamlit; faça mudanças incrementais e testadas.

## Comandos (PowerShell, na raiz)

```powershell
python --version
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m pip_audit -r requirements.txt
```

Pipeline e dashboard:

```powershell
.\.venv\Scripts\python.exe build_pipeline.py "data\incoming\Teste_Tecnico_Dados_Candidato_20260825.zip" --output "data\output" --quarantine "data\quarantine"
.\.venv\Scripts\python.exe -m streamlit run dashboard.py
.\.venv\Scripts\python.exe export_csv.py
```

## Regras

- Use Python 3.14.5 e somente dependências declaradas em `requirements.txt`.
- Trate `data/incoming/` como imutável; nunca mova, extraia, regrave ou duplique a entrada original.
- Direcione aprovados e relatórios a `data/output/` e rejeitados a `data/quarantine/`; testes devem usar `tmp_path`.
- Preserve rastreabilidade, catálogo de qualidade, precisão decimal e publicação com rollback.
- Não adicione regras de negócio silenciosamente nem reescreva a arquitetura funcional.
- Não versione dados, resultados, bancos, ambientes virtuais, caches ou temporários.
- Não adicione cloud, Docker, banco externo, autenticação, MCP ou serviços sem requisito explícito.
- Use `pathlib`; evite suposições Unix e valide no Windows.
- Toda mudança comportamental exige teste e atualização do README/SECURITY quando aplicável.
- Antes de entregar, execute as verificações, `git diff --check` e revise o diff completo.
- Faça commits pequenos somente quando solicitados; nunca faça push, merge, rebase destrutivo ou force push sem autorização explícita.
