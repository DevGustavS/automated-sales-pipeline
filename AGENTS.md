# AGENTS.md

## Objetivo

Manter um pipeline local, simples, reproduzível e compatível com Windows. Nesta fase, preserve somente a fundação: não implemente o pipeline nem a interface.

## Comandos (PowerShell, na raiz)

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m pip_audit -r requirements.txt
```

## Regras

- Use Python 3.14.5 e apenas as dependências de `requirements.txt`.
- Preserve o enunciado e o ZIP fornecido sem mover, extrair, alterar ou duplicar.
- Trate `data/incoming/` como imutável; grave derivados somente em `data/processed/`, `data/quarantine/` ou `output/`.
- Não versione dados locais, resultados, bancos DuckDB, ambientes virtuais ou temporários.
- Não adicione cloud, Docker, banco externo, autenticação, MCP ou complexidade sem requisito explícito.
- Use `pathlib` para caminhos e evite suposições específicas de Unix.
- Toda implementação futura deve incluir testes e atualizar o mapeamento do README.
- Antes de entregar, execute as verificações aplicáveis e revise `git diff`; não faça commit automaticamente.
