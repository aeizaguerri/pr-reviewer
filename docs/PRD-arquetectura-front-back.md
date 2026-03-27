# PRD: Arquitectura Frontend-Backend Separados

**Versión:** 1.2  
**Fecha:** 2026-03-27  
**Estado:** Listo para implementación  
**Proyecto:** PR Code Reviewer

---

## 1. Contexto y Objetivos

### 1.1 Contexto Actual

El proyecto actual tiene una **arquitectura monolítica** donde:

- **Streamlit** (`streamlit_app.py`) contiene tanto la UI como la lógica de negocio
- El agente de revisión (`src/reviewer/agent.py`) se importa y ejecuta directamente desde Streamlit
- **FastAPI** (`main.py`) solo existe como webhook de GitHub, sin endpoint para consumo externo
- No hay separación entre frontend y backend

### 1.2 Problemas de la Arquitectura Actual

| Problema | Impacto |
|----------|---------|
| Acoplamiento UI-Lógica | Cambios en UI afectan la lógica de negocio |
| No escalable | No se puede escalar front y back independientemente |
| Difícil testing | No se puede testear la API sin UI |
| No reusable | La lógica no puede ser consumida por otros clientes |
| Debugging complejo | Logs mezclados entre UI y lógica |

### 1.3 Objetivo

Transformar la aplicación en una arquitectura **REST tradicional** con:

- **Frontend**: Streamlit que consume la API
- **Backend**: FastAPI con endpoints REST
- **Despliegue**: Dos contenedores Docker separados, tanto en local como en Render

---

## 2. Arquitectura Propuesta

### 2.1 Diagrama de Componentes

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                                  RENDER                                      │
│                                                                              │
│   ┌─────────────────────────┐         ┌─────────────────────────────────┐  │
│   │      FRONTEND           │         │          BACKEND                │  │
│   │                         │   HTTP  │                                 │  │
│   │  ┌───────────────────┐  │────────▶│  ┌───────────────────────────┐ │  │
│   │  │ Streamlit         │  │         │  │ FastAPI                   │ │  │
│   │  │                   │  │         │  │                           │ │  │
│   │  │ - UI              │  │         │  │ POST /api/v1/review       │ │  │
│   │  │ - Form inputs    │  │         │  │ POST /api/v1/webhook/gh  │ │  │
│   │  │ - Display results│  │         │  │ GET  /health              │ │  │
│   │  │                   │  │         │  │ GET  /api/v1/providers   │ │  │
│   │  │                   │  │         │  │                           │ │  │
│   │  │ llama a backend  │  │◀────────│  │ - Orquesta agentes       │ │  │
│   │  └───────────────────┘  │         │  │ - Consulta Neo4j         │ │  │
│   │                         │         │  │ - Devuelve resultados     │ │  │
│   │    Puerto 8501          │         │  └───────────────────────────┘ │  │
│   │                         │         │         Puerto 8000             │  │
│   └─────────────────────────┘         └─────────────────────────────────┘  │
│                                                                              │
│                                                                              │
│   ┌──────────────────────────────────────────────────────────────────────┐   │
│   │                         NEO4J AURA (Cloud)                          │   │
│   │                                                                       │   │
│   │   Knowledge Graph para análisis de impacto entre repositorios       │   │
│   │                                                                       │   │
│   └──────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 Servicios de Despliegue

Cada servicio tiene su propio **Dockerfile** y se despliega como contenedor Docker tanto en local como en Render.

| Servicio | Tecnología | Puerto | Dockerfile | Entorno |
|----------|-----------|--------|------------|---------|
| `pr-reviewer-web` | Streamlit | 8501 | `frontend/Dockerfile` | Local + Render |
| `pr-reviewer-api` | FastAPI | 8000 | `backend/Dockerfile` | Local + Render |
| Neo4j | AuraDB | - | N/A (cloud) | Solo cloud |

#### Estrategia de contenedores

- **Local**: `docker-compose.yml` en la raíz levanta ambos servicios a la vez
- **Render**: cada servicio se despliega de forma independiente apuntando a su Dockerfile
- **Neo4j**: se usa siempre la instancia en Aura (no se dockeriza Neo4j)

### 2.3 Comunicación entre Componentes

```
┌─────────────┐  httpx/JSON  ┌─────────────┐  neo4j driver  ┌─────────────┐
│  Streamlit  │─────────────▶│  FastAPI    │───────────────▶│    Neo4j    │
│  (Frontend) │              │  (Backend)  │                │   (Data)    │
└─────────────┘              └──────┬──────┘                └─────────────┘
                                    │ httpx
                                    ▼
                             ┌─────────────┐
                             │  GitHub API │
                             │  + LLM API  │
                             └─────────────┘
```

- **Frontend → Backend**: `httpx` con timeout configurable via `BACKEND_TIMEOUT`
- **Backend → GitHub/LLM**: `httpx` y `PyGithub` (ya existentes en `src/reviewer/tools.py`)
- **Backend → Neo4j**: driver oficial `neo4j` via Bolt (ya existente en `src/knowledge/client.py`)

---

## 3. Requisitos Funcionales

### 3.1 Endpoints del Backend

#### 3.1.1 POST /api/v1/review

Ejecuta una revisión de PR.

**Request:**
```json
{
  "owner": "octocat",
  "repo": "Hello-World",
  "pr_number": 42,
  "provider": "cerebras",
  "api_key": "hf_...",
  "model_override": "meta-llama/Llama-3.1-8B-Instruct:cerebras",
  "base_url_override": "",
  "github_token": "ghp_..."
}
```

> `base_url_override` es opcional. Se usa cuando el provider es `ollama` o cuando el usuario quiere apuntar a un endpoint custom.

**Response:**
```json
{
  "summary": "...",
  "approved": true,
  "bugs": [
    {
      "file": "src/main.py",
      "line": 42,
      "severity": "major",
      "description": "...",
      "suggestion": "..."
    }
  ],
  "impact_warnings": [
    {
      "description": "...",
      "affected_services": ["..."]
    }
  ]
}
```

#### 3.1.2 GET /api/v1/providers

Devuelve la lista de proveedores disponibles.

**Response:**
```json
{
  "providers": {
    "cerebras": {
      "base_url": "https://router.huggingface.co/v1",
      "key_label": "HuggingFace API Key",
      "default_model": "meta-llama/Llama-3.1-8B-Instruct:cerebras",
      "description": "FREE - 1M tokens/day, very fast",
      "supports_structured_output": true
    },
    "openai": { ... },
    "huggingface": { ... },
    "ollama": { ... }
  }
}
```

#### 3.1.3 GET /health

Health check para Render. Verifica conectividad con Neo4j si `ENABLE_GRAPH_ENRICHMENT=true`.

**Response (healthy):**
```json
{
  "status": "healthy",
  "version": "0.1.0",
  "neo4j": "connected"
}
```

**Response (degraded — Neo4j no alcanzable):**
```json
{
  "status": "degraded",
  "version": "0.1.0",
  "neo4j": "unreachable"
}
```

> Siempre retorna HTTP 200. Render usa este endpoint para verificar que el proceso está vivo, no para verificar dependencias externas. La info de Neo4j es informativa.

#### 3.1.4 POST /api/v1/webhook/github

Recibe eventos de webhook de GitHub y dispara revisiones automáticamente.

> **Diferencia clave con `/api/v1/review`**: este endpoint NO recibe credenciales del usuario. Lee `GITHUB_ACCESS_TOKEN` y las credenciales del LLM desde variables de entorno del backend. Es un endpoint de sistema, no de usuario.

**Request:** Payload JSON del webhook de GitHub (action: `opened`, `synchronize`)

**Response:**
```json
{
  "status": "reviewed",
  "approved": true,
  "bugs_found": 3,
  "summary": "..."
}
```

**Response (evento ignorado):**
```json
{
  "status": "skipped",
  "reason": "action 'closed' not handled"
}
```

### 3.2 Funcionalidades del Frontend

| ID | Funcionalidad | Descripción |
|----|---------------|-------------|
| F1 | Formulario de revisión | Ingresar owner, repo, PR number |
| F2 | Selección de proveedor | Elegir LLM provider desde backend |
| F3 | Configuración de API keys | Input para API keys (no se almacenan) |
| F4 | Ejecución de review | Llamar al backend y mostrar spinner |
| F5 | Visualización de resultados | Mostrar summary, bugs, warnings |
| F6 | Manejo de errores | Mostrar errores de forma amigable |

### 3.3 Flujo de Usuario

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  Usuario     │     │   Streamlit  │     │   FastAPI    │     │    GitHub    │
│  ingresa     │────▶│  valida      │────▶│  ejecuta     │────▶│  obtiene     │
│  datos PR    │     │  inputs      │     │  review      │     │  diff        │
└──────────────┘     └──────────────┘     └──────────────┘     └──────────────┘
                                                    │
                                                    ▼
                                            ┌──────────────┐
                                            │    Neo4j     │
                                            │  impacto     │
                                            └──────────────┘
```

---

## 4. Cambios Requeridos

### 4.1 Estructura de Archivos Actual vs Nueva

#### Actual:

```
proyecto/
├── streamlit_app.py      # UI + lógica mezclada
├── main.py              # Solo webhook
├── src/
│   ├── reviewer/
│   │   ├── agent.py     # Lógica de review
│   │   ├── models.py    # Modelos Pydantic
│   │   └── ...
│   ├── ui/
│   │   └── config_adapter.py
│   └── knowledge/
│       └── ...
├── Procfile             # Solo streamlit
└── pyproject.toml
```

#### Nueva:

```
proyecto/
├── frontend/
│   ├── streamlit_app.py  # Solo UI
│   ├── Dockerfile        # Imagen Docker del frontend
│   ├── pyproject.toml    # Dependencias del frontend
│   └── .streamlit/
│       └── config.toml
├── backend/
│   ├── main.py              # FastAPI con endpoints
│   ├── Dockerfile            # Imagen Docker del backend
│   ├── pyproject.toml        # Dependencias del backend
│   ├── api/
│   │   └── v1/
│   │       └── routes.py
│   ├── core/
│   │   └── config.py
│   ├── models/
│   │   └── schemas.py        # Pydantic schemas de la API REST
│   └── services/
│       └── reviewer.py       # Orquestación: fusión de agent.py actual
├── src/                      # Código compartido — NO se mueve, el backend lo usa directamente
│   ├── reviewer/
│   │   ├── agent.py          # Se mantiene — reviewer.py lo importa
│   │   ├── tools.py          # Se mantiene — fetch_pr_data, post_review_comments
│   │   ├── prompts.py        # Se mantiene — REVIEWER_INSTRUCTIONS
│   │   └── models.py         # Se mantiene — BugReport, ReviewOutput
│   └── knowledge/            # Se mantiene — Neo4j client, queries, schema
├── docker-compose.yml    # Orquestación local (frontend + backend)
├── .env.example          # Variables de entorno de referencia
└── pyproject.toml        # Workspace raíz
```

### 4.2 Lista de Tareas por Componente

#### 4.2.1 Backend (FastAPI)

| ID | Tarea | Tipo | Depende de |
|----|-------|------|------------|
| B1 | Crear `backend/main.py` con FastAPI base | Nuevo | - |
| B2 | Definir Pydantic schemas para requests/responses | Nuevo | - |
| B3 | Migrar lógica de `agent.py` a `services/reviewer.py` | Refactor | - |
| B4 | Implementar endpoint POST `/api/v1/review` | Nuevo | B2, B3 |
| B5 | Implementar endpoint GET `/api/v1/providers` | Nuevo | - |
| B6 | Implementar endpoint GET `/health` (incluyendo verificación de conectividad Neo4j) | Nuevo | - |
| B7 | Migrar webhook de `main.py` a `/api/v1/webhook/github` | Migrar | - |
| B8 | Crear `backend/Dockerfile` | Nuevo | - |
| B9 | Configurar CORS para permitir frontend | Nuevo | B1 |
| B10 | Configurar variables de entorno | Config | - |
| B11 | **[Seguridad]** Asegurar que `github_token` y `api_key` nunca aparezcan en logs del backend | Seguridad | B1 |

#### 4.2.2 Frontend (Streamlit)

| ID | Tarea | Tipo | Depende de |
|----|-------|------|------------|
| F1 | Crear directorio `frontend/` | Estructura | - |
| F2 | Mover `streamlit_app.py` a `frontend/` | Migrar | - |
| F3 | Modificar para llamar a API en vez de agente directo | Refactor | B4 |
| F4 | Obtener providers desde API (GET `/api/v1/providers`) | Nuevo | B5 |
| F5 | Eliminar imports de `src.reviewer.agent` | Refactor | F3 |
| F6 | Configurar URL del backend via env var `BACKEND_URL` | Nuevo | - |
| F7 | Crear `frontend/Dockerfile` | Nuevo | - |
| F8 | Crear `.streamlit/config.toml` | Config | - |
| F9 | **[Seguridad]** Verificar que todos los campos de credenciales preservan `type="password"` (ya existe, no romper) | Seguridad | F2 |

#### 4.2.3 Compartido

| ID | Tarea | Tipo | Depende de |
|----|-------|------|------------|
| C1 | `src/` se mantiene intacto — el backend lo importa directamente | Decisión | - |
| C2 | Mover `src/ui/config_adapter.py` a `backend/core/providers.py` | Migrar | - |
| C3 | Actualizar `pyproject.toml` workspace raíz para reflejar nueva estructura | Config | C2 |
| C4 | Crear `docker-compose.yml` para entorno local | Nuevo | B8, F7 |
| C5 | Crear `.env.example` con todas las variables separadas por servicio | Nuevo | B10, F6 |

#### 4.2.4 Despliegue

| ID | Tarea | Tipo | Depende de |
|----|-------|------|------------|
| D1 | Probar contenedores en local con docker-compose | Testing | C4 |
| D2 | Crear cuenta en Render (si no existe) | Setup | - |
| D3 | Desplegar backend en Render (imagen Docker) | Deploy | B8, D2 |
| D4 | Desplegar frontend en Render (imagen Docker) | Deploy | F7, D2 |
| D5 | Configurar variables de entorno en Render (ver sección 6.3) | Config | D3, D4 |
| D6 | Configurar Neo4j Aura con credenciales | Setup | - |
| D7 | **[Seguridad]** Generar `GITHUB_WEBHOOK_SECRET` y configurar webhook en GitHub + Render | Seguridad | D3 |
| D8 | Probar flujo completo end-to-end en producción | Testing | D3, D4, D6, D7 |

---

## 5. Modelos de Datos

### 5.1 Request Schemas

```python
# backend/models/schemas.py
from pydantic import BaseModel
from typing import Optional

class ReviewRequest(BaseModel):
    owner: str
    repo: str
    pr_number: int
    provider: str = "cerebras"
    api_key: str
    model_override: Optional[str] = None
    base_url_override: Optional[str] = None  # Para Ollama o endpoints custom
    github_token: Optional[str] = None

class ProviderInfo(BaseModel):
    base_url: str
    key_label: str
    default_model: str
    description: str
    supports_structured_output: bool
```

### 5.2 Response Schemas

```python
class BugReport(BaseModel):
    file: str
    line: int
    severity: str  # "critical", "major", "minor"
    description: str
    suggestion: str

class ImpactWarning(BaseModel):
    description: str
    affected_services: list[str]

class ReviewResponse(BaseModel):
    summary: str
    approved: bool
    bugs: list[BugReport]
    impact_warnings: list[ImpactWarning]
```

---

## 6. Consideraciones Técnicas

### 6.1 Timeout

Las llamadas al agente pueden tomar tiempo considerable (especialmente con modelos gratuitos). Configurar:

- **Frontend → Backend**: 300 segundos (5 minutos)
- **Backend → LLM**: 180 segundos (3 minutos)
- **Render**: El tier gratis no tiene timeout específico, pero se recomienda configurar

### 6.2 Seguridad

#### 6.2.1 Riesgo: Credenciales de usuario en tránsito

**Descripción del problema (arquitectura actual)**

En la implementación actual, el `github_token` sigue este camino dentro del mismo proceso:

```
Browser del usuario
    → st.text_input()                          ← token ingresado por el usuario
    → review_pr_with_config(github_token=token) ← pasado como argumento en memoria
    → post_review_comments(github_token=token)
        → Header: "Authorization: Bearer {token}"
```

Al no existir separación entre frontend y backend, el token no viaja por la red — todo ocurre en el mismo proceso Python. Sin embargo, el token se pasa como argumento a través de toda la cadena de funciones, lo que lo expone a riesgos de logging accidental.

**En la nueva arquitectura**

Con frontend y backend separados, el `github_token` DEBE viajar por la red (del frontend al backend vía HTTP). Esto aplica igualmente a las LLM API keys (`provider_api_key`). Ambas credenciales tienen **el mismo perfil de riesgo**: viajan en el body del request.

Mover el `github_token` exclusivamente a una env var del backend resolvería el tránsito, pero **rompe el producto**: los usuarios no podrían acceder a sus propios repositorios privados ni postear comentarios con su propia cuenta de GitHub.

**Conclusión: ambas credenciales son credenciales de usuario, no de sistema.**

```
Browser del usuario
    → POST /api/v1/review  {github_token, api_key, ...}   ← viajan cifradas (HTTPS)
    → Backend las usa para llamar a GitHub y al LLM        ← nunca las persiste
    → Response                                             ← credenciales descartadas
```

**Mitigaciones requeridas:**

| Mitigación | Dónde aplicar |
|------------|---------------|
| **HTTPS obligatorio** | Render lo provee automáticamente en ambos servicios |
| **Nunca loguear tokens** | Backend: excluir `github_token` y `api_key` de cualquier log |
| **Nunca persistir tokens** | Backend: no almacenar credenciales en DB, cache ni disco |
| **Tiempo de vida mínimo** | Backend: usar el token en el request y descartarlo inmediatamente |

**Cambios requeridos en el código:**

| Componente | Cambio |
|------------|--------|
| `backend/services/reviewer.py` | Asegurar que los tokens nunca aparezcan en logs |
| `backend/main.py` | Configurar el logger para enmascarar campos sensibles |

#### 6.2.2 Otras consideraciones de seguridad

| Aspecto | Consideración |
|---------|---------------|
| LLM API Keys | Credenciales del usuario, viajan cifradas. Nunca se loguean ni almacenan |
| GitHub Token | Credenciales del usuario, viajan cifradas. Nunca se loguean ni almacenan |
| CORS | Configurar en backend solo para el dominio del frontend de Render |
| Neo4j | Credenciales del sistema, solo en variables de entorno del backend |
| Secrets en Docker | Usar variables de entorno, nunca hardcodear en Dockerfile |

### 6.3 Variables de Entorno

#### Backend (`backend/.env`):
```
# Neo4j
NEO4J_URI=neo4j+s://...
NEO4J_USER=neo4j
NEO4J_PASSWORD=...

# Knowledge Graph
ENABLE_GRAPH_ENRICHMENT=true
GRAPH_QUERY_TIMEOUT=5
MAX_IMPACT_WARNINGS=10

# Webhook (credenciales de sistema, no de usuario)
GITHUB_ACCESS_TOKEN=ghp_...
DEFAULT_PROVIDER=cerebras
DEFAULT_MODEL=meta-llama/Llama-3.1-8B-Instruct:cerebras
HUGGING_FACE_API_KEY=hf_...

# CORS — dominio del frontend (local o Render)
CORS_ORIGINS=http://localhost:8501,https://pr-reviewer-web.onrender.com
```

#### Frontend (`frontend/.env` — desarrollo local):
```
# Apunta al servicio backend en docker-compose (nombre del servicio)
BACKEND_URL=http://backend:8000

# Timeout para llamadas al backend (en segundos)
BACKEND_TIMEOUT=300
```

#### Frontend en Render (env vars configuradas en el dashboard):
```
BACKEND_URL=https://pr-reviewer-api.onrender.com
BACKEND_TIMEOUT=300
```

> **Importante**: En docker-compose, el frontend usa `http://backend:8000` (nombre del servicio Docker), NO `http://localhost:8000`. En Render, usa la URL pública del backend.

### 6.4 Seguridad del Webhook (GitHub Webhook Secret)

El endpoint `POST /api/v1/webhook/github` usa credenciales del sistema (`GITHUB_ACCESS_TOKEN`, `HUGGING_FACE_API_KEY`). Sin protección, cualquiera que conozca la URL podría activarlo y consumir la cuota de API del propietario.

#### Mecanismo de protección: HMAC-SHA256

GitHub firma cada request con un secreto compartido. El backend valida la firma antes de procesar:

```
GitHub → POST /webhook {X-Hub-Signature-256: sha256=<hmac(secret, body)>}
               ↓
Backend: recalcula hmac(secret, body) y compara
    ✅ Coincide → 202 Accepted
    ❌ No coincide → 401 Unauthorized
    ⚠️  Secret no configurado → 501 Not Implemented
```

#### Comportamiento según configuración

| `GITHUB_WEBHOOK_SECRET` | Resultado |
|------------------------|-----------|
| No configurado | `501 Not Implemented` — webhook deshabilitado |
| Configurado, firma inválida | `401 Unauthorized` |
| Configurado, firma válida | `202 Accepted` — review disparado |

#### Pasos para configurar en producción (tarea D7)

**Paso 1 — Generar el secreto:**
```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
# → a3f8b2c1d4e5f6a7b8c9d0e1f2a3b4c5...
```

**Paso 2 — Configurar en GitHub:**
`Repo → Settings → Webhooks → Add webhook`
- Payload URL: `https://pr-reviewer-api.onrender.com/api/v1/webhook/github`
- Content type: `application/json`
- Secret: el valor generado en Paso 1
- Events: `Pull requests` (opened, synchronize)

**Paso 3 — Configurar en Render:**
Agregar env var en el servicio backend:
```
GITHUB_WEBHOOK_SECRET=<el mismo valor del Paso 1>
```

> **Importante**: El secreto debe ser idéntico en GitHub y en Render. Solo funciona para los repos donde vos configurés el webhook manualmente.

### 6.5 Docker

#### 6.5 Estrategia de build

- **Base image**: `python:3.14-slim` para ambos servicios
- **Gestor de dependencias**: `uv` (ya usado en el proyecto)
- **Multi-stage build**: No requerido para este proyecto (sin assets compilados)
- **Usuario no-root**: Buena práctica de seguridad en ambos Dockerfiles

#### Entornos

| Entorno | Cómo se levanta | Backend URL |
|---------|-----------------|-------------|
| **Local** | `docker-compose up` | `http://backend:8000` |
| **Render** | Deploy independiente por servicio | `https://pr-reviewer-api.onrender.com` |

---

## 7. Testing

### 7.1 Backend Tests

| Test | Descripción |
|------|-------------|
| `test_health_ok` | GET /health retorna 200 con `status: healthy` |
| `test_health_neo4j_unreachable` | GET /health retorna 200 con `status: degraded` si Neo4j no responde |
| `test_providers` | GET /api/v1/providers retorna todos los providers con sus campos |
| `test_review_success` | POST /api/v1/review con datos válidos retorna `ReviewResponse` |
| `test_review_missing_fields` | POST /api/v1/review sin campos obligatorios retorna 422 |
| `test_review_invalid_pr` | POST /api/v1/review con PR inexistente retorna error descriptivo |
| `test_webhook_opened` | POST /webhook con action `opened` dispara review |
| `test_webhook_skipped` | POST /webhook con action `closed` retorna `status: skipped` |

### 7.2 Errores HTTP esperados

| Código | Cuándo ocurre |
|--------|---------------|
| `200` | Request exitoso |
| `202` | Webhook aceptado |
| `401` | Firma de webhook inválida |
| `422` | Validación fallida (campos requeridos ausentes o tipo incorrecto) |
| `500` | Error interno del agente o GitHub API |
| `501` | Webhook deshabilitado (`GITHUB_WEBHOOK_SECRET` no configurado) |
| `504` | Timeout del agente LLM |

### 7.3 Integration Tests

| Test | Descripción |
|------|-------------|
| `test_e2e_review` | Flujo completo: form → POST /api/v1/review → GitHub → LLM → resultado |

---

## 8. Riesgos y Mitigaciones

| Riesgo | Probabilidad | Impacto | Mitigación |
|--------|--------------|---------|------------|
| **Credenciales de usuario logueadas accidentalmente** | Media | **Crítico** | Configurar logger del backend para enmascarar campos sensibles (ver 6.2.1) |
| **Webhook sin secreto expuesto en producción** | Alta (si no se configura) | **Crítico** | Configurar `GITHUB_WEBHOOK_SECRET` en Render (tarea D7, ver sección 6.4) — sin él, el endpoint devuelve 501 |
| Tier gratis de Render se suspende por mucho tráfico | Media | Alto | Monitorear uso, upgrade si es necesario |
| Neo4j Aura se suspende por inactividad | Baja | Medio | Configurar alertas, reactivar manualmente |
| Timeout en reviews largos | Media | Medio | Configurar timeout adecuado, mostrar mensaje |
| Cambios rompen compatibilidad | Baja | Alto | Tests, versionado de API |

---

## 9. Milestones

### Milestone 1: Backend API + Docker
- [ ] B1-B7, B9-B11: Backend con endpoints funcionales y seguridad
- [ ] B8: `backend/Dockerfile`
- [ ] Tests unitarios del backend

### Milestone 2: Frontend Refactorizado + Docker
- [ ] F1-F8: Frontend consume API
- [ ] F7: `frontend/Dockerfile`
- [ ] F9: Campos de credenciales seguros en UI
- [ ] Tests de integración

### Milestone 3: Entorno Local Completo
- [ ] C4: `docker-compose.yml` funcional
- [ ] C5: `.env.example`
- [ ] D1: Prueba E2E en local con docker-compose

### Milestone 4: Despliegue en Render
- [ ] D2-D6: Servicios desplegados con variables de entorno configuradas
- [ ] D7: Webhook secret generado y configurado en GitHub + Render
- [ ] D8: Prueba E2E en producción

---

## 10. Referencias

- [Render - Deploy Docker Images](https://render.com/docs/deploying-an-image)
- [Render - Docker](https://render.com/docs/docker)
- [FastAPI](https://fastapi.tiangolo.com/)
- [Streamlit](https://docs.streamlit.io/)
- [Neo4j Aura](https://neo4j.com/cloud/aura/)
- [uv - Docker](https://docs.astral.sh/uv/guides/integration/docker/)
- [Docker Compose](https://docs.docker.com/compose/)
