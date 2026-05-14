# IMPT — Intelligent Mutation Prioritization Tool

**NovaSoft · FEU Institute of Technology · A.Y. 2025–2026**

Cost-effective mutation testing for FOSS projects using intelligent mutant prioritization and selection.

---

## System Requirements

| Component | Minimum | Recommended |
|---|---|---|
| OS | Ubuntu 22.04 LTS | Ubuntu 24.04 LTS |
| CPU | 2 vCPU | 4 vCPU |
| RAM | 4 GB | 8 GB |
| Storage | 40 GB SSD | 80 GB SSD |
| Python | 3.12+ | 3.12 |
| Node.js | 18 LTS+ | 20 LTS |
| Docker | CE 24+ | CE 27+ with Compose plugin |

---

## Local Development Setup

### 1. Clone the repository

```bash
git clone git@github.com:ChingDE/IMPT.git
cd IMPT
```

### 2. Set up the Python environment

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Configure environment

```bash
cp .env.example .env
# Edit .env — local dev defaults (SQLite) work without changes
```

### 4. Run the test suite

```bash
PYTHONPATH=. python -m pytest tests/ -v
# Expected: 83 passed
```

### 5. Start the API server

```bash
PYTHONPATH=. python scripts/run_local.py
# API: http://127.0.0.1:8000
# Docs: http://127.0.0.1:8000/docs
```

### 6. Start the frontend

```bash
cd frontend/src
npm install
npm run dev
# Frontend: http://localhost:3000
```

### 7. Run the algorithm demo (no Docker needed)

```bash
PYTHONPATH=. python cli/run_demo.py --mutants 40 --budget 300 --kill-rate 0.72
```

---

## Production Deployment

See `IMPT_v2_Redeployment_Guide.docx` for the complete step-by-step guide.

### Quick reference

```bash
# On the Droplet (as imptuser):
cd ~/impt
git pull origin main
docker compose up -d --build

# Verify:
curl http://localhost:8000/api/health
# Expected: {"status":"ok","version":"2.0.0","db":"ok","worker":"ok (celery)"}
```

### Enable auto-start on reboot (NFR079)

```bash
sudo systemctl enable impt
sudo systemctl status impt
```

---

## Project Structure

```
impt/
├── impt/                   # Core algorithm engine
│   ├── algorithms/         # 5 IMPT algorithms
│   │   ├── scoring.py      # Algorithm 1 — Multi-Factor Scoring
│   │   ├── subsumption.py  # Algorithm 2 — Subsumption Reduction
│   │   ├── optimization.py # Algorithm 3 — Knapsack Time-Budget
│   │   ├── extrapolation.py# Algorithm 4 — Wilson CI Extrapolation
│   │   └── time_estimation.py # Algorithm 5 — Execution Time Estimator
│   ├── models/             # Domain models (Mutant, Project, Result)
│   └── engine.py           # IMPTEngine orchestrator
├── adapters/               # PIT (Java) and Stryker (JS) adapters
├── api/                    # FastAPI application
│   ├── routers/            # Endpoint handlers
│   └── schemas/            # Pydantic request/response models
├── db/                     # Database layer
│   ├── models/             # SQLAlchemy ORM models
│   └── repositories/       # Data access layer
├── worker/                 # Celery task queue
├── services/               # Email service (Resend)
├── frontend/src/           # React frontend (Vite)
├── tests/                  # 83 tests (unit, integration, API, adapter)
├── scripts/                # Local dev server, migrations
├── deploy/                 # Dockerfile, docker-compose, Caddy, systemd
└── cli/                    # Algorithm demo CLI
```

---

## Environment Variables

See `.env.example` for all variables. Key ones:

| Variable | Description |
|---|---|
| `DATABASE_URL` | PostgreSQL async connection string |
| `REDIS_URL` | Upstash Redis (Celery broker) |
| `SECRET_KEY` | JWT signing key (64-char hex) |
| `RESEND_API_KEY` | Resend email API key |
| `ALLOWED_ORIGINS` | CORS allowed frontend URLs |

---

## API Documentation

Interactive API docs available at `/docs` (Swagger UI) when the server is running.

---

## Running Tests

```bash
# All tests
PYTHONPATH=. python -m pytest tests/ -v

# Unit tests only
PYTHONPATH=. python -m pytest tests/unit/ -v

# API tests
PYTHONPATH=. python -m pytest tests/api/ -v
```

---

## Team

- Daniel Emile F. Ching
- Jacy Ahrone N. Laurente
- James Lawrence C. Vicente

**Adviser:** Dr. Angelo C. Arguson  
**Course:** CS0033 — Software Engineering  
**Term:** 3rd Term, A.Y. 2025–2026
