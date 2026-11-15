# WikiGuardian

**AI-assisted Wikipedia edit verification — built on MariaDB vector search (RAG) and system-versioned tables (SVT).**

WikiGuardian intercepts a proposed Wikipedia edit, extracts its factual claims, checks them against Wikipedia's own knowledge **and** real-world sources, weighs how contested the article is over time, and **blocks false information before it is published** — while keeping a human in the loop for the final decision.

Built for the **Junction 2026 "Wikipedia Through Time" challenge by MariaDB** (both tracks: RAG + SVT).

---

## What it does

- **Live intercept:** edit an article in a Wikipedia-style UI, hit *Save*, and WikiGuardian verifies it in real time — streaming each step and stopping contradicted edits.
- **RAG (MariaDB Vector):** internal retrieval over a Wikipedia corpus with `VEC_DISTANCE_COSINE` (BGE-M3, 1024-dim), plus external web research.
- **SVT (System-Versioned Tables):** `article_history` holds full Wikipedia revision history (`FOR SYSTEM_TIME AS OF` time-travel, revert/edit-war detection) that feeds the verdict; `guardian_article_state` records WikiGuardian's own editorial state over time.
- **Seven-agent pipeline:** Planner → Claim Extractor → Knowledge Retriever (internal) + Research Agent (external) → Verification → adversarial Critique → Confidence & Decision.
- **Audit + human review:** every run is persisted; a reviewer makes the final approve/reject call.

## Two interfaces

| UI | Stack | Purpose |
|----|-------|---------|
| **WikiGuardianpedia** | FastAPI + static Vector-skin frontend | The live "Wikipedia clone" demo: edit → save → streamed verification → block |
| **Admin app** | Streamlit | Dashboard, Submit Edit, Review Queue, History, point-in-time viewer |

## Architecture

```
app/
  agents/         planner, claim_extractor, knowledge_retriever, research_agent,
                  verification_agent, critique_agent, decision_agent, LLM clients
  orchestrator/   verification_orchestrator.py  (the seven-agent workflow)
  services/       verification, persistence, temporal, article_state, article,
                  proposal, review, history, dashboard, embedding, database
  schemas/        pydantic contracts (verification, persistence)
  providers/      LLM provider factory
  ui/             Streamlit pages (incl. wikipedia.py live demo)
  api/            FastAPI backend (server.py, SSE streaming)
  web/            Wikipedia Vector-skin frontend (index.html, style.css, app.js)
migrations/       001-006 (incl. system-versioned article_state + article_history)
schema.sql        full reconstructed base schema (source of truth)
import_dataset_*.py   loaders for MariaDB Wikipedia Datasets S (vectors) and M (history)
```

## Setup

Requires **Python 3.11+**, **MariaDB 11.7+** (vector + system versioning; developed on 11.8), and **Ollama** with `bge-m3` for embeddings.

```bash
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
# plus: fastapi uvicorn (for the clone UI), streamlit (for the admin app)
```

1. **Database:** create the `wikiguardian` database, then apply the schema and migrations:
   ```
   mysql -u root -p < schema.sql
   mysql -u root -p wikiguardian -e "source migrations/006_article_history_svt.sql"
   ```
2. **Datasets:** download MariaDB's [Wikipedia datasets](https://github.com/MariaDB/mariadb-wikipedia-datasets) (S for vectors, M for history) and load them:
   ```
   python import_dataset_s.py          # current articles + BGE-M3 vectors
   python import_dataset_m.py --pages 5842,32957,1256,440,1275,6021,1150   # revision history (subset)
   ```
3. **Embeddings:** `ollama pull bge-m3` (server on `localhost:11434`).
4. **Environment (`.env`, never committed):** set the variable *names* below to your own values:
   `LLM_PROVIDER`, `OPENAI_COMPATIBLE_URL`, `OPENAI_COMPATIBLE_API_KEY`, `OPENAI_COMPATIBLE_MODEL`,
   `OXYLABS_WEB_API_KEY`, `DB_PASSWORD` (and optionally `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_NAME`, `OLLAMA_URL`).

## Running

```bash
# WikiGuardianpedia (the live clone demo)
.venv\Scripts\python.exe -m uvicorn app.api.server:app --port 8600   # http://localhost:8600

# Admin app (dashboard / review queue / history)
.venv\Scripts\python.exe -m streamlit run app\ui\main.py             # http://localhost:8501
```

## Notes

- AI results are **advisory**; a human makes the final publication decision — WikiGuardian never auto-publishes.
- The `mariadb-*` reference projects and large datasets are intentionally gitignored.

## License

See upstream data licenses: Wikipedia text is CC BY-SA 4.0; MariaDB's dataset scripts are MIT.
