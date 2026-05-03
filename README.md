# IMPT — Intelligent Mutation Prioritization Tool
**NovaSoft | FEU Institute of Technology**

> Cost-Effective Mutation Testing Utilizing Intelligent Mutation Operator Prioritization and Selection on Free/Libre and Open-Source Software

---

## Quick start (local white-box testing — no Docker needed)

```bash
# Install deps
pip install -r requirements.txt

# Run tests (207 tests, no external services required)
PYTHONPATH=. python -m pytest tests/ -v

# Start API (uses SQLite, sync job runner)
PYTHONPATH=. python scripts/run_local.py
# Open: http://127.0.0.1:8000/docs

# Run algorithm demo
PYTHONPATH=. python cli/run_demo.py --mutants 40 --budget 300 --kill-rate 0.72
```

---

## Project structure

```
impt/
├── impt/                          Core algorithm engine (zero external deps)
│   ├── algorithms/
│   │   ├── scoring.py             Algorithm 1 — Multi-Factor Scoring
│   │   ├── subsumption.py         Algorithm 2 — 4-Stage Subsumption
│   │   ├── optimization.py        Algorithm 3 — Knapsack Time-Budget Optimizer
│   │   ├── extrapolation.py       Algorithm 4 — Wilson CI Extrapolation
│   │   └── time_estimation.py     Algorithm 5 — Execution Time Estimator
│   ├── engine.py                  Orchestration pipeline
│   └── models/                    Mutant, Project, Result data models
│
├── adapters/                      Framework integration
│   ├── pit_adapter.py             PIT (Java/Maven/Gradle) — runs + parses XML
│   ├── stryker_adapter.py         Stryker (JS/TS) — runs + parses JSON
│   └── factor_enricher.py         Static analysis: complexity, git, security
│
├── api/                           FastAPI REST backend
│   ├── routers/
│   │   ├── auth.py                POST /register, /token; GET /me
│   │   ├── projects.py            CRUD /api/projects
│   │   ├── upload.py              POST /api/projects/{id}/upload
│   │   ├── jobs.py                POST /api/jobs; GET status/result/mutants
│   │   └── health.py              GET /api/health
│   ├── middleware.py              Rate limiting + request size enforcement
│   └── schemas/                   Pydantic v2 request/response schemas
│
├── db/                            Database layer
│   ├── database.py                Async SQLAlchemy engine + session factory
│   ├── models/orm_models.py       User, ProjectRecord, MutationJob, MutantRecord
│   └── repositories/              Data access — no raw SQL in routers
│
├── worker/                        Async job execution
│   ├── celery_app.py              Celery app (graceful fallback if Redis absent)
│   ├── tasks.py                   run_mutation_job — real adapters + synthetic fallback
│   └── watchdog.py                Celery beat task: recover stuck jobs every 5 min
│
├── frontend/index.html            Single-file SPA (auth, dashboard, upload, results)
│
├── sandbox/Dockerfile             Isolated execution image (JDK 17 + Node 20 + PIT + Stryker)
├── Dockerfile                     API + worker production image
├── docker-compose.yml             Full stack: nginx + api + worker + beat + db + redis
├── deploy/
│   ├── nginx/nginx.conf           Reverse proxy (HTTP default; HTTPS opt-in)
│   ├── nginx/ssl/                 Place fullchain.pem + privkey.pem here
│   └── setup_vps.sh               One-script Ubuntu 22.04/24.04 bootstrap
├── scripts/migrations/            Alembic migration files
├── config/settings.py             All config via environment variables
├── requirements.txt               Python dependencies
├── .env.example                   Environment variable template
└── .gitignore / .dockerignore
```

---

## VPS deployment

### Prerequisites
- Ubuntu 22.04 or 24.04 VPS (min 2 vCPU, 4 GB RAM)
- Domain name pointed at the VPS IP

### Deploy

```bash
# 1. Clone repo on the VPS
git clone https://github.com/novasoft/impt.git /opt/impt
cd /opt/impt

# 2. Configure environment
cp .env.example .env
# Edit .env — set POSTGRES_PASSWORD, SECRET_KEY, and your domain in ALLOWED_ORIGINS

# 3. Build sandbox image (JDK + Node + PIT + Stryker; takes ~5 min first time)
docker build -t impt-sandbox:latest ./sandbox/

# 4. Start the full stack
docker compose up -d --build

# 5. Run database migrations
docker compose exec api alembic upgrade head

# 6. Open http://your-vps-ip in a browser
```

### Enable HTTPS (after DNS propagates)

```bash
apt install certbot
certbot certonly --standalone -d your-domain.com
cp /etc/letsencrypt/live/your-domain.com/fullchain.pem deploy/nginx/ssl/
cp /etc/letsencrypt/live/your-domain.com/privkey.pem   deploy/nginx/ssl/
# Uncomment the HTTPS server block in deploy/nginx/nginx.conf
docker compose restart nginx
```

### Useful commands

```bash
docker compose logs -f api worker     # Live logs
docker compose ps                     # Service status
docker compose exec api alembic upgrade head  # Run migrations
docker compose down -v                # Full teardown (deletes data)
```

---

## Test suite

| Suite | Tests | Coverage |
|---|---|---|
| Unit — algorithms | 83 | 95% |
| Unit — adapters | 81 | 91% |
| Integration — pipeline | 13 | 94% |
| API — endpoints | 30 | 88% |
| **Total** | **207** | **~93%** |

```bash
PYTHONPATH=. python -m pytest tests/ -v --cov=impt --cov=api --cov=adapters --cov=worker
```

---

## Supported FOSS projects

| Framework | Language | Build tool | Requirements |
|---|---|---|---|
| PIT | Java | Maven | pom.xml in project root |
| PIT | Java | Gradle | build.gradle in project root |
| Stryker | JavaScript | npm/yarn | package.json in project root |
| Stryker | TypeScript | npm/yarn | package.json + tsconfig.json |

Maximum upload size: 50 MB (configurable via `MAX_UPLOAD_MB` env var).
