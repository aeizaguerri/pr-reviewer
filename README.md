# PR Code Reviewer

Revisor automatizado de pull requests usando [Agno](https://docs.agno.com) y múltiples proveedores LLM (HuggingFace, OpenAI, Ollama). Analiza el diff de un PR de GitHub, detecta bugs e inyecta comentarios inline directamente en la revisión.

Opcionalmente, integra un **Knowledge Graph en Neo4j** para detectar impacto cross-repo: si un PR toca un contrato, esquema o ruta que otro servicio consume, el revisor lo advierte automáticamente en el análisis.

## Arquitectura

```
┌─────────────────────┐   HTTP    ┌─────────────────────┐
│  Frontend           │──────────▶│  Backend            │
│  Streamlit :8501    │           │  FastAPI :8000       │
│  (UI + form)        │◀──────────│  (lógica + agentes)  │
└─────────────────────┘           └──────────┬──────────┘
                                             │ Bolt
                                   ┌─────────▼──────────┐
                                   │  Neo4j Aura         │
                                   │  (Knowledge Graph)  │
                                   └─────────────────────┘
```

- **Frontend** (`frontend/`): UI Streamlit pura. Envía credenciales y datos del PR al backend via HTTP. Sin lógica de dominio.
- **Backend** (`backend/`): API REST FastAPI. Orquesta el agente LLM, consulta el Knowledge Graph y postea comentarios en GitHub.
- **src/**: Capa de dominio compartida (reviewer, knowledge graph). Importada directamente por el backend.

## Proveedores LLM soportados

| Proveedor | Descripción | Coste |
|-----------|-------------|-------|
| **Cerebras** (via HuggingFace router) | Muy rápido, structured outputs | Gratis (1M tokens/día) |
| **HuggingFace** | Modelos hosted en HF Inference API | Gratis |
| **OpenAI** | API oficial de OpenAI | De pago |
| **Ollama** | Modelos locales | Gratis (local) |

## Requisitos

- Python >= 3.14
- [uv](https://docs.astral.sh/uv/) (gestor de paquetes)
- Docker + Docker Compose (para desarrollo local completo)

## Inicio rápido (Docker Compose)

```bash
# 1. Clonar el repositorio
git clone <url-del-repositorio>
cd <carpeta-del-repositorio>

# 2. Configurar variables de entorno
cp .env.example .env
# Editar .env con tus credenciales

# 3. Levantar todos los servicios (backend + frontend + neo4j)
docker compose up --build

# Frontend disponible en: http://localhost:8501
# Backend API en:         http://localhost:8000
# Neo4j Browser en:       http://localhost:7474
```

## Configuración

Copia `.env.example` a `.env` y completa las variables:

```env
# ── Backend ──────────────────────────────────────────────────────────────────

# Neo4j (usa Neo4j Aura en producción)
NEO4J_URI=neo4j+s://xxxx.databases.neo4j.io
NEO4J_USER=neo4j
NEO4J_PASSWORD=tu_password

# Knowledge Graph (desactivado por defecto)
ENABLE_GRAPH_ENRICHMENT=false

# Webhook GitHub (credenciales de sistema)
GITHUB_ACCESS_TOKEN=ghp_tu_token
GITHUB_WEBHOOK_SECRET=tu_secreto_webhook   # genera con: openssl rand -hex 32

# LLM provider
DEFAULT_PROVIDER=cerebras
DEFAULT_MODEL=moonshotai/Kimi-K2-Instruct  # modelo por defecto
HUGGING_FACE_API_KEY=hf_tu_key
HUGGING_FACE_API_URL=https://router.huggingface.co/v1
OLLAMA_API_URL=http://localhost:11434/v1   # solo si usás el provider ollama

# CORS — URL del frontend
CORS_ORIGINS=http://localhost:8501

# Logging
LOG_LEVEL=INFO                             # DEBUG | INFO | WARNING | ERROR | CRITICAL

# Opik (observabilidad LLM — opcional, desactivado si no se define OPIK_API_KEY)
OPIK_API_KEY=                              # obtén tu key en app.comet.com
OPIK_PROJECT_NAME=pr-reviewer              # nombre del proyecto en Opik
OPIK_WORKSPACE=                            # workspace de Opik (opcional)

# ── Frontend ──────────────────────────────────────────────────────────────────
BACKEND_URL=http://backend:8000            # en docker-compose usa el nombre del servicio
```

El token de GitHub necesita permisos `repo` (repositorios privados) o `public_repo` (públicos).

## Uso via interfaz web

Abre `http://localhost:8501` en el navegador:

1. **Sidebar**: selecciona el proveedor LLM e introduce tu API key
2. **Formulario**: introduce el owner, repo y número de PR de GitHub
3. **Revisar**: el backend analiza el diff, consulta el grafo y devuelve el resultado
4. Los bugs detectados se postean automáticamente como comentarios inline en el PR

## Uso via CLI

```bash
# Iniciar el servidor API (backend solo)
uv run python -m backend.main serve
```

## Knowledge Graph (detección de impacto cross-repo)

### ¿Para qué sirve?

Cuando varios servicios comparten contratos (eventos, esquemas, APIs), un cambio en un repositorio puede romper silenciosamente a los consumidores. El módulo `src/knowledge/` modela esas dependencias en un grafo Neo4j y las inyecta como contexto en el prompt del LLM antes de la revisión.

### Modelo de grafo

**Nodos**

| Label | Descripción |
|---|---|
| `Repository` | Repositorio Git |
| `Service` | Microservicio o aplicación |
| `Contract` | Contrato entre servicios (evento, API, mensaje) |
| `Schema` | Esquema de datos (JSON Schema, Avro, Protobuf…) |
| `Field` | Campo individual de un schema |

**Relaciones**

| Relación | Significado |
|---|---|
| `OWNS` | Un repositorio o servicio posee un contrato/schema |
| `PRODUCES` | Un servicio produce un contrato |
| `CONSUMES` | Un servicio consume un contrato |
| `DEFINES` | Un contrato define un schema |
| `HAS_FIELD` | Un schema tiene un campo |

### Poblar el grafo

```bash
# 1. Inicializar constraints e índices en Neo4j
NEO4J_URI=... NEO4J_USER=neo4j NEO4J_PASSWORD=... \
uv run python -m backend.main graph init

# 2. Importar topología de servicios desde YAML
NEO4J_URI=... NEO4J_USER=neo4j NEO4J_PASSWORD=... \
uv run python -m backend.main graph import examples/topology.yaml

# 3. Verificar entidades en el grafo
uv run python -m backend.main graph query OrderCreatedEvent
uv run python -m backend.main graph query src/models/order.py --by-path
```

### Formato del fichero de topología (YAML)

Consulta `examples/topology.yaml` para un ejemplo completo. Estructura básica:

```yaml
repositories:
  - name: order-service
    url: https://github.com/org/order-service
    services:
      - name: OrderService
        produces:
          - name: OrderCreatedEvent
            file_path: src/events/order_created.py
            schemas:
              - name: OrderSchema
                file_path: src/schemas/order.py
                fields:
                  - name: order_id
                    type: string
```

## Despliegue en Render

El repositorio incluye `render.yaml` para despliegue con un solo click:

1. **Render → New → Blueprint** → conectar este repositorio
2. Render crea automáticamente dos servicios Docker (`pr-reviewer-api` y `pr-reviewer-web`)
3. Completar las env vars secretas en el dashboard de Render
4. Actualizar `CORS_ORIGINS` (backend) y `BACKEND_URL` (frontend) con las URLs públicas asignadas
5. *(Opcional)* Configurar webhook en GitHub → `https://<backend>.onrender.com/api/v1/webhook/github`

> El endpoint del webhook valida la firma HMAC-SHA256. Si `GITHUB_WEBHOOK_SECRET` no está configurado, devuelve `501 Not Implemented` (seguro por defecto).

## Estructura del proyecto

```text
.
├── backend/                     # Servicio backend (FastAPI)
│   ├── main.py                  # Entrypoint: FastAPI app + CLI + webhook
│   ├── api/v1/routes.py         # Endpoints REST: /review, /providers, /health
│   ├── core/
│   │   ├── config.py            # BackendConfig (env vars + CORS_ORIGINS)
│   │   └── providers.py         # PROVIDERS dict + build_provider_config()
│   ├── models/schemas.py        # DTOs Pydantic: ReviewRequest, ReviewResponse…
│   ├── services/reviewer.py     # Orquestador: adapter entre API y domain layer
│   ├── Dockerfile               # Imagen Docker del backend
│   └── pyproject.toml           # Dependencias del backend
├── frontend/                    # Servicio frontend (Streamlit)
│   ├── streamlit_app.py         # UI: form + httpx calls al backend
│   ├── Dockerfile               # Imagen Docker del frontend
│   └── pyproject.toml           # Dependencias del frontend (streamlit + httpx)
├── prompts/
│   └── reviewer_instructions.txt # Prompt del agente (versionado + fallback Opik)
├── src/                         # Capa de dominio (importada por backend)
│   ├── core/
│   │   ├── config.py            # Config: variables de entorno
│   │   ├── observability.py     # Opik: configure_opik(), get_reviewer_prompt(), track_if_enabled()
│   │   ├── logging_config.py    # Logging centralizado
│   │   └── exceptions.py        # Excepciones personalizadas (GraphError…)
│   ├── knowledge/               # Módulo Knowledge Graph
│   │   ├── client.py            # Driver Neo4j: get_driver(), check_health()
│   │   ├── schema.py            # Constraints, índices, init_schema()
│   │   ├── models.py            # TopologyConfig, ImpactWarning, ImpactResult
│   │   ├── population.py        # load_topology() + populate_graph()
│   │   └── queries.py           # find_consumers_of_paths(), search_entities()
│   └── reviewer/
│       ├── agent.py             # Agno Agent + review_pr_with_config()
│       ├── models.py            # BugReport, ReviewOutput
│       ├── prompts.py           # REVIEWER_INSTRUCTIONS + _build_impact_section()
│       └── tools.py             # fetch_pr_data() + post_review_comments()
├── tests/                       # 121 tests unitarios
├── examples/
│   └── topology.yaml            # Ejemplo de topología de servicios
├── docker-compose.yml           # Orquestación local: backend + frontend + neo4j
├── render.yaml                  # Render IaC: deploy automático en Render
├── .env.example                 # Plantilla de variables de entorno
└── pyproject.toml               # Metadata del proyecto raíz
```

## API REST (backend)

| Método | Endpoint | Descripción |
|--------|----------|-------------|
| `POST` | `/api/v1/review` | Ejecuta revisión de PR, devuelve `ReviewResponse` |
| `GET` | `/api/v1/providers` | Lista proveedores LLM disponibles |
| `GET` | `/health` | Health check (siempre HTTP 200) |
| `POST` | `/api/v1/webhook/github` | Webhook GitHub (requiere `GITHUB_WEBHOOK_SECRET`) |

## Tests

```bash
# Tests unitarios (sin dependencias externas)
uv run pytest tests/ -m "not integration"

# Todos los tests (requiere Neo4j y credenciales reales)
uv run pytest tests/
```

Los 214 tests cubren los módulos `core`, `reviewer`, `knowledge` y `observability`.
