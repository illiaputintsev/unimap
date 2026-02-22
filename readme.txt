# StudentRoadmap

An AI-powered learning platform that generates personalised academic roadmaps for university students. Students search for their course, get an AI-generated module dependency graph, and track their progress through quizzes and topic mastery.

---

## Features

- **Course discovery** — search UK universities and courses via Discover Uni data
- **AI roadmap generation** — Gemini extracts modules, builds a dependency graph, and lays out a visual roadmap
- **Interactive graph** — vis-network visualisation with clusters, draggable modal, and progress badges on nodes
- **Module workspace** — AI-generated topics, three quiz modes (Practice, Focused, Mock Exam), PDF note upload
- **Progress tracking** — per-topic mastery percentages, overall progress bar, level and XP system
- **Achievements** — badge system tied to progress milestones
- **User profiles** — saved roadmaps, statistics, shareable links

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | HTML5, CSS3, Vanilla JS, [vis-network](https://visjs.github.io/vis-network/) |
| Backend | Django 6, Django REST Framework, SimpleJWT |
| Database | PostgreSQL (prod), SQLite3 (dev) |
| AI | Google Gemini 2.5 Flash |
| Storage | Google Cloud Storage (optional) |
| Deployment | Google Cloud Run (backend + frontend), nginx |

---

## Project Structure

```
studentroadmap/
├── frontend/
│   ├── index.html          # Home — course search & roadmap generation
│   ├── roadmap.html        # Interactive roadmap graph
│   ├── module.html         # Module workspace (topics, quizzes, notes)
│   ├── quiz.html           # Quiz interface
│   ├── progress.html       # Progress dashboard
│   ├── profile.html        # User profile
│   ├── api-service.js      # API client (all backend calls)
│   └── theme.css           # Global styles
├── backend/
│   ├── config/             # Django settings & URL routing
│   ├── accounts/           # Auth (register, JWT login)
│   ├── courses/            # University & course catalog, module drafts
│   ├── roadmaps/           # Roadmap generation, graph, progress
│   ├── quizzes/            # Quiz generation, PDF notes, workspace state
│   ├── requirements.txt
│   └── manage.py
├── nginx.conf              # nginx config for frontend Cloud Run service
├── Dockerfile.frontend     # Docker image for frontend
├── cloudbuild.yaml         # Cloud Build config
└── proxy-server.js         # Local CORS proxy for development
```

---

## Local Development

### Prerequisites

- Python 3.12+
- PostgreSQL (or use SQLite for dev)
- Node.js (only for local proxy server)
- A Google Gemini API key

### Backend

```bash
cd backend

python3.12 -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate

pip install -r requirements.txt

# Copy and fill in environment variables
cp .env.example .env
```

`.env` variables:

```
DB_NAME=studentmap_db
DB_USER=studentdb_user
DB_PASSWORD=yourpassword
DB_HOST=127.0.0.1
DB_PORT=5432

GEMINI_API_KEY=your_gemini_key
GEMINI_MODEL=gemini-2.5-flash
```

> Leave `DB_*` empty to fall back to SQLite3 automatically.

```bash
python manage.py migrate
python manage.py runserver
# API available at http://localhost:8000
```

### Frontend

```bash
cd frontend
python3 -m http.server 5500
# Open http://localhost:5500
```

Or open any `.html` file directly with VS Code Live Server.

### Local CORS Proxy (if calling production API from local frontend)

```bash
node proxy-server.js
# Listens on http://127.0.0.1:8081
```

---

## Deployment

The project runs two Cloud Run services:

| Service | Description |
|---|---|
| `studentroadmap-api` | Django backend |
| `studentroadmap-frontend` | nginx serving static frontend |

### Deploy frontend

```bash
# In Cloud Shell at repo root
git pull origin main

gcloud builds submit --config cloudbuild.yaml --project <PROJECT_ID>

gcloud run deploy studentroadmap-frontend \
  --image europe-west2-docker.pkg.dev/<PROJECT_ID>/cloud-run-source-deploy/studentroadmap-frontend \
  --region europe-west2 \
  --platform managed \
  --allow-unauthenticated \
  --port 8080 \
  --project <PROJECT_ID>
```

### Deploy backend

```bash
cd backend

gcloud run deploy studentroadmap-api \
  --source . \
  --region europe-west2 \
  --platform managed \
  --allow-unauthenticated \
  --project <PROJECT_ID>
```

---

## API Overview

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/auth/register/` | Register a new user |
| POST | `/api/auth/token/` | Obtain JWT token pair |
| POST | `/api/auth/token/refresh/` | Refresh access token |
| GET | `/api/catalog/universities/` | Search universities |
| GET | `/api/catalog/courses/` | Search courses |
| POST | `/api/catalog/courses/{id}/modules/draft/` | AI-generate module draft |
| POST | `/api/roadmaps/generate/` | Generate a new roadmap |
| GET | `/api/roadmaps/` | List user's roadmaps |
| GET | `/api/roadmaps/{id}/graph/` | Get graph (nodes + edges) |
| PATCH | `/api/roadmaps/{id}/graph/topics/{topic_id}/progress/` | Update topic mastery |
| POST | `/api/quizzes/module-quiz/generate/` | Generate a quiz |
| POST | `/api/quizzes/module-notes/` | Upload a PDF note |

---

## Environment Variables Reference

| Variable | Required | Description |
|---|---|---|
| `GEMINI_API_KEY` | Yes | Google Gemini API key |
| `GEMINI_MODEL` | No | Model name (default: `gemini-2.5-flash`) |
| `DB_NAME` | No | PostgreSQL database name |
| `DB_USER` | No | PostgreSQL user |
| `DB_PASSWORD` | No | PostgreSQL password |
| `DB_HOST` | No | PostgreSQL host |
| `DB_PORT` | No | PostgreSQL port |
| `SECRET_KEY` | Yes (prod) | Django secret key |
| `ALLOWED_HOSTS` | Yes (prod) | Comma-separated allowed hostnames |
| `CSRF_TRUSTED_ORIGINS` | Yes (prod) | Comma-separated trusted origins |
| `GCS_BUCKET_NAME` | No | Google Cloud Storage bucket for media |
