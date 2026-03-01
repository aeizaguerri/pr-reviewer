# PR Code Reviewer

Revisor automatizado de pull requests usando [Agno](https://docs.agno.com) y múltiples proveedores LLM (HuggingFace, OpenAI, Ollama). Analiza el diff de un PR de GitHub, detecta bugs e inyecta comentarios inline directamente en la revisión.

## Proveedores soportados

- **HuggingFace** — Modelos hospedados en HuggingFace Inference API (por defecto)
- **OpenAI** — API oficial de OpenAI
- **Ollama** — Modelos locales con Ollama

## Requisitos

- Python >= 3.14
- [uv](https://docs.astral.sh/uv/) (gestor de paquetes recomendado)

## Instalación

```bash
# Clonar el repositorio
git clone <url-del-repositorio>
cd <carpeta-del-repositorio>

# Copiar el fichero de configuración y editar con tus API keys
cp dummy.env .env

# Instalar dependencias con uv
uv sync
```

## Configuración

Edita el archivo `.env` con tus credenciales. Las variables disponibles son:

```env
# HuggingFace
HUGGING_FACE_API_KEY=tu_api_key
HUGGING_FACE_API_URL=https://router.huggingface.co/v1

# OpenAI (opcional)
OPENAI_API_KEY=tu_api_key

# Ollama (opcional)
OLLAMA_API_URL=http://localhost:11434/v1

# GitHub (necesario para leer PRs y publicar comentarios)
GITHUB_ACCESS_TOKEN=tu_github_token

# Proveedor y modelo por defecto
DEFAULT_MODEL=moonshotai/Kimi-K2-Instruct
DEFAULT_PROVIDER=huggingface
```

El token de GitHub necesita permisos `repo` (repositorios privados) o `public_repo` (públicos).

## Uso

### Revisar un PR desde la CLI

```bash
uv run python main.py review <owner/repo> <pr_number>

# Con salida detallada (debug)
uv run python main.py review <owner/repo> <pr_number> --debug
```

Ejemplo:

```bash
uv run python main.py review octocat/Hello-World 42
```

### Iniciar el servidor webhook (modo producción)

```bash
uv run python main.py serve
```

El servidor arranca en `http://0.0.0.0:8000` y expone el endpoint `POST /webhook/github`. Configura un webhook en tu repositorio de GitHub apuntando a esa URL con el evento `pull_request`.

## Estructura del proyecto

```text
.
├── main.py                  # CLI (review / serve) + FastAPI webhook
├── src/
│   ├── core/
│   │   ├── config.py        # Config: variables de entorno + get_model_config()
│   │   └── exceptions.py    # Excepciones personalizadas
│   └── reviewer/
│       ├── agent.py         # Agno Agent + review_pr() + review_pr_debug()
│       ├── models.py        # BugReport, ReviewOutput (schemas Pydantic)
│       ├── prompts.py       # REVIEWER_INSTRUCTIONS (system prompt)
│       └── tools.py         # fetch_pr_data() + post_review_comments()
├── tests/                   # Tests unitarios
├── pyproject.toml           # Configuración del proyecto
├── dummy.env                # Plantilla de variables de entorno
└── .env                     # Variables de entorno (no incluido en git)
```

## Dependencias principales

- `agno` — Framework de agentes LLM (abstracción multi-proveedor + output estructurado)
- `openai` — Cliente para APIs compatibles con OpenAI (usado internamente por Agno)
- `pygithub` — Lectura de PRs y diffs desde la API de GitHub
- `httpx` — Publicación de comentarios de revisión inline vía GitHub REST API
- `fastapi[standard]` — Servidor webhook para integración en producción
- `python-dotenv` — Carga de variables de entorno desde `.env`
