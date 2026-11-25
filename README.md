# Mestre de D&D

Aplicação solo de D&D 5e com separação entre estado determinístico em Python (FastAPI) e narração via Gemini API.

## Configuração

1. Copie `.env.example` para `.env` e preencha `GEMINI_API_KEY`.
2. Crie e ative um ambiente virtual e instale as dependências:

```bash
python -m venv .venv
pip install -r backend/requirements.txt
```

## Execução Local

```bash
uvicorn backend.main:app --reload
```

Acesse `http://localhost:8000`.

## Execução com Docker Compose

```bash
docker compose up --build
```

## Testes

```bash
pytest
```
