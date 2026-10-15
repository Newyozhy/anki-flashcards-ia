# AnkiCraft AI ⚡
> **Generador Inteligente de Flashcards y Estudio Curricular para Anki con Arquitectura Hexagonal, React 19 y Gemini 3.8 Flash**

AnkiCraft AI es una plataforma web local diseñada para transformar cualquier contenido educativo (apuntes de texto, documentos PDF, capturas de pantalla, diagramas o mazos existentes de Anki) en flashcards atómicas de alta retención optimizadas para **Spaced Repetition (SRS)** y **Active Recall**, inyectándolas automáticamente en **Anki Desktop** mediante **AnkiConnect** o exportándolas como paquetes **`.apkg`** independientes.

Además de la generación, incluye **Deck Studio**: un centro de control curricular con grafos de precedencia conceptual (DAG), auditoría neurocognitiva según las 20 reglas de Piotr Wozniak, entrevistas diagnósticas socráticas y saneamiento quirúrgico transaccional con preservación de historial FSRS.

---

## 🏛️ Arquitectura del Sistema

El proyecto está diseñado bajo los principios de **Arquitectura Hexagonal (Ports & Adapters)** y **Clean Code**:

```text
       [ React 19 + Tailwind Frontend ]
                      │
                      ▼ (REST API - 52 Endpoints)
            [ FastAPI Controllers ]
                      │
  ┌───────────────────┴───────────────────┐
  │         Dominio & Casos de Uso        │
  │   - Generación & Cockpit Pre-flight   │
  │   - Deck Studio & Grafo DAG NetworkX  │
  │   - Saneamiento Quirúrgico & FSRS     │
  └───────────────────┬───────────────────┘
                      │
           [ Puertos (Interfaces) ]
            ├── ICardGeneratorPort ──► [ Gemini 3.8 Flash / Resilient Cascade / Ollama GPU ]
            ├── IAnkiBridgePort    ──► [ AnkiConnectAdapter / GenankiFileAdapter ]
            └── IEmbeddingPort     ──► [ GeminiEmbeddingAdapter (text-embedding-004) ]
                                                │
                                                ▼ (SQLite)
                                      [ DeckKnowledgeStore ]
```

### Tecnologías & Herramientas
* **Backend:** Python 3.14 + FastAPI + Pydantic v2 + Uvicorn + HTTPX + NetworkX.
* **Motor de IA (Cloud):** Google GenAI SDK con modelo **`gemini-3.8-flash`** (Structured Outputs) respaldado por `ResilientCascadeAdapter` (Gemini $\to$ NVIDIA NIM $\to$ Groq $\to$ OpenRouter) con circuit breakers.
* **Motor de IA (Local GPU):** Ollama en `localhost:11434` (soporta `llama3.2:3b`, `qwen2.5:14b` y visión multimodal con `qwen2.5vl:7b`).
* **Base de Conocimiento Local:** Repositorio vectorial en SQLite (`backend/data/deck_knowledge.db`) con clustering esférico K-Means y búsqueda por similitud de cosenos.
* **Integración Anki:**
  * **AnkiConnect:** JSON-RPC local en `localhost:8765` para sincronización directa y refactorización in-situ preservando FSRS.
  * **Genanki:** Generación de archivos binarios `.apkg` con soporte para modelos Básicos y Cloze deletion.
* **Frontend:** React 19 + TypeScript 5.8 + Vite 6 + Tailwind CSS v4 + Lucide Icons + KaTeX.

---

## 🚀 Inicio Rápido (1 Clic en Windows)

1. **Obtené tu API Key gratuita de Gemini:**
   * Ingresá a [Google AI Studio](https://aistudio.google.com/app/apikey) y creá una clave API gratuita.
   * Pegala en `backend/.env` en la variable `GEMINI_API_KEY=` (o ingresala en el botón "API Key" de la web).
2. **Ejecutá el launcher:**
   * Hacé doble clic en el archivo `start.bat` en la raíz del proyecto.
   * El script levantará el backend en `http://127.0.0.1:8000`, el frontend en `http://localhost:5173` y te abrirá el navegador automáticamente.
3. **(Opcional) Ejecución 100% Local y Offline con Ollama (GPU):**
   * Hacé doble clic en `start_local_models.bat` en la raíz del proyecto.
   * Podrás desplegar modelos locales como **`qwen2.5:14b`** o **`qwen2.5vl:7b`** (multimodal) y alternar en la web a `🖥️ Local (GPU)`.

---

## 🔌 Configuración de Anki Desktop (Opcional pero Recomendado)

Para que las tarjetas se sincronicen directamente sin tener que importar archivos:
1. Abrí **Anki Desktop**.
2. Andá a `Herramientas` > `Complementos` > `Descargar complementos...`.
3. Pegá el código de **AnkiConnect**: `2055492159` y dale a Aceptar.
4. Reiniciá Anki.
5. *(Opcional)* En `Herramientas` > `Complementos` > Seleccioná `AnkiConnect` > `Configuración`, verificá que incluya `"webBindPort": 8765`.

> **Nota:** Si Anki no está abierto, AnkiCraft AI te permite descargar el paquete `.apkg` con un clic para abrirlo cuando quieras.

---

## 🧪 Pruebas y Certificación de Calidad

El sistema cuenta con **158 pruebas automatizadas** que garantizan 100% cero regresiones:

```powershell
# 1. Tests de regresión del backend (119 tests)
cd backend
.\.venv\Scripts\python -m pytest tests -q

# 2. Auditorías pedagógicas y fuzzing Schemathesis (33 tests, Niveles 1 a 6)
cd backend
.\.venv\Scripts\python -m pytest audits -v

# 3. Tests E2E de frontend con Playwright (6 tests de integración)
cd frontend
npm run test:e2e
```

---

## 📚 Documentación Técnica Detallada

Para consultar la arquitectura en profundidad, convenciones y mapas de trazabilidad:
* [**`docs/INDEX.md`**](docs/INDEX.md): Índice maestro para agentes de IA y desarrolladores, con metadata YAML estructurada y matriz de características a código.
* [**`docs/ARCHITECTURE.md`**](docs/ARCHITECTURE.md): Guía completa de arquitectura hexagonal, cascada multi-proveedor y subsistemas.
* [**`docs/CONVENTIONS.md`**](docs/CONVENTIONS.md): Estándares de código, reglas de TypeScript, Python 3.14 y neurociencia de Wozniak.
* [**`docs/ROADMAP.md`**](docs/ROADMAP.md): Hitos completados vs backlog activo.
* [**`docs/AUDIT_FINDINGS.md`**](docs/AUDIT_FINDINGS.md): Certificación técnica de auditorías Niveles 1 a 6 y F1 a F6.
* [**`docs/SANITATION_WORKFLOW_AUDIT.md`**](docs/SANITATION_WORKFLOW_AUDIT.md): Diagnóstico y hoja de ruta para la unificación del saneamiento en Deck Studio.
