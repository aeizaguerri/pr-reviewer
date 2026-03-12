# PR Code Reviewer

Revisor automatizado de pull requests usando [Agno](https://docs.agno.com) y múltiples proveedores LLM (HuggingFace, OpenAI, Ollama). Analiza el diff de un PR de GitHub, detecta bugs e inyecta comentarios inline directamente en la revisión.

Opcionalmente, integra un **Knowledge Graph en Neo4j** para detectar impacto cross-repo: si un PR toca un contrato, esquema o ruta que otro servicio consume, el revisor lo advierte automáticamente en el análisis.

## Proveedores soportados

- **HuggingFace** — Modelos hospedados en HuggingFace Inference API (por defecto)
- **OpenAI** — API oficial de OpenAI
- **Ollama** — Modelos locales con Ollama

## Requisitos

- Python >= 3.14
- [uv](https://docs.astral.sh/uv/) (gestor de paquetes recomendado)
- Docker + Docker Compose (opcional, para el Knowledge Graph con Neo4j)

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

# Neo4j Knowledge Graph (opcional)
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=changeme
ENABLE_GRAPH_ENRICHMENT=false
GRAPH_QUERY_TIMEOUT=5
MAX_IMPACT_WARNINGS=10
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

### Comandos del Knowledge Graph

```bash
# Inicializar constraints e índices en Neo4j
uv run python main.py graph init

# Importar topología de servicios desde un fichero YAML
uv run python main.py graph import examples/topology.yaml

# Buscar una entidad en el grafo por nombre
uv run python main.py graph query OrderCreatedEvent

# Buscar consumidores de una ruta de fichero concreta
uv run python main.py graph query src/models/order.py --by-path

# Listar todos los consumidores de una entidad
uv run python main.py graph query OrderCreatedEvent --consumers
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

### Flujo de revisión enriquecida

```
PR diff
  └─▶ extract changed paths
        └─▶ query graph → downstream consumers
              └─▶ build impact section (ImpactWarning list)
                    └─▶ inject into LLM prompt
                          └─▶ review with cross-repo awareness
                                └─▶ ReviewOutput (bugs + impact_warnings)
```

### Feature toggle y degradación elegante

El enrichment está **desactivado por defecto** (`ENABLE_GRAPH_ENRICHMENT=false`). Cuando está desactivado, o si Neo4j no está disponible, la revisión continúa exactamente igual que sin el módulo. No hay errores bloqueantes.

### Formato del fichero de topología (YAML)

```yaml
repositories:
  - name: order-service
    url: https://github.com/org/order-service
    services:
      - name: OrderService
        produces:
          - name: OrderCreatedEvent
            path: src/events/order_created.py
            schema:
              fields:
                - name: order_id
                  type: string
                - name: amount
                  type: float
        consumes: []

  - name: payment-service
    url: https://github.com/org/payment-service
    services:
      - name: PaymentService
        produces: []
        consumes:
          - name: OrderCreatedEvent
            from_service: OrderService
```

Consulta `examples/topology.yaml` para un ejemplo realista con tres servicios.

## Quick Start con Knowledge Graph

```bash
# 1. Levantar Neo4j con Docker
docker compose up -d

# 2. Habilitar el enrichment en .env
echo "ENABLE_GRAPH_ENRICHMENT=true" >> .env

# 3. Inicializar el schema en Neo4j
uv run python main.py graph init

# 4. Importar la topología de ejemplo
uv run python main.py graph import examples/topology.yaml

# 5. Revisar un PR con detección de impacto cross-repo activa
uv run python main.py review octocat/Hello-World 42
```

## Estructura del proyecto

```text
.
├── main.py                      # CLI (review / serve / graph) + FastAPI webhook
├── docker-compose.yml           # Neo4j 5 Community Edition
├── examples/
│   └── topology.yaml            # Ejemplo de topología de servicios
├── src/
│   ├── core/
│   │   ├── config.py            # Config: variables de entorno + get_model_config()
│   │   └── exceptions.py        # Excepciones personalizadas (incl. GraphError)
│   ├── knowledge/
│   │   ├── __init__.py          # API pública del módulo
│   │   ├── client.py            # Driver Neo4j: get_driver(), close_driver(), check_health()
│   │   ├── schema.py            # Constraints, índices, constantes, init_schema()
│   │   ├── models.py            # TopologyConfig, ImpactWarning, ImpactResult (Pydantic)
│   │   ├── population.py        # load_topology() + populate_graph() con MERGE atómico
│   │   └── queries.py           # find_consumers_of_paths(), find_consumers(), search_entities()
│   └── reviewer/
│       ├── agent.py             # Agno Agent + review_pr() + enrichment step
│       ├── models.py            # BugReport, ReviewOutput (incl. impact_warnings)
│       ├── prompts.py           # REVIEWER_INSTRUCTIONS + _build_impact_section()
│       └── tools.py             # fetch_pr_data() + post_review_comments()
├── tests/                       # Tests unitarios (94 tests)
├── pyproject.toml               # Configuración del proyecto
├── dummy.env                    # Plantilla de variables de entorno
└── .env                         # Variables de entorno (no incluido en git)
```

## Dependencias principales

- `agno` — Framework de agentes LLM (abstracción multi-proveedor + output estructurado)
- `openai` — Cliente para APIs compatibles con OpenAI (usado internamente por Agno)
- `pygithub` — Lectura de PRs y diffs desde la API de GitHub
- `httpx` — Publicación de comentarios de revisión inline vía GitHub REST API
- `fastapi[standard]` — Servidor webhook para integración en producción
- `python-dotenv` — Carga de variables de entorno desde `.env`
- `neo4j` — Driver oficial de Neo4j (Knowledge Graph)
- `pyyaml` — Parsing de ficheros de topología YAML

## Tests

```bash
uv run pytest
```

Los 94 tests cubren los módulos `core`, `reviewer` y `knowledge` (client, schema, models, population, queries).
