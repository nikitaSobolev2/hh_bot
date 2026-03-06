# HH Bot — HeadHunter Vacancy Parser Telegram Bot

Telegram bot that scrapes HeadHunter (hh.ru) vacancies, extracts keywords using AI, and generates resume key phrases to help users build better resumes.

## Features

- **Vacancy parsing** — scrape HH.ru search results, extract descriptions and skill tags
- **AI keyword extraction** — send vacancy descriptions to OpenAI and aggregate the most common technologies/skills
- **Key phrase generation** — AI-generated resume bullet points with streaming output to Telegram
- **Blacklist system** — per-user, per-search-context vacancy deduplication with configurable expiry
- **Multi-format export** — view results as Telegram message, download as `.md` or `.txt`
- **Admin panel** — manage users (ban, balance, messaging), toggle tasks, edit app settings, circuit breaker controls
- **Role-based access** — `admin` and `user` roles with granular permissions stored in DB
- **i18n (infrastructure ready)** — Fluent translation files for Russian and English, locale middleware, `aiogram-i18n` configured; handler wiring pending
- **Celery background tasks** — parsing and AI generation run asynchronously with idempotency, circuit breakers, and timeout controls
- **Structured logging** — console (Rich), rotating file, and Telegram channel (ERROR+)
- **Payment & referral preparation** — balance transactions, referral codes, deep link handling (stubs ready for integration)

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Language | Python 3.12+ |
| Bot framework | aiogram 3.x |
| Database | PostgreSQL 16 + SQLAlchemy 2.0 (async via asyncpg) |
| Migrations | Alembic |
| Task queue | Celery 5.x + Redis 7 |
| HTTP client | httpx (async) |
| AI | OpenAI API (AsyncOpenAI with streaming) |
| Config | pydantic-settings |
| Logging | structlog + Rich |
| HTML parsing | BeautifulSoup4 |
| Testing | pytest + pytest-asyncio + pytest-mock |
| Linting | Ruff |
| Containerization | Docker + Docker Compose |

## Project Structure

```
hh_bot/
├── docker-compose.yml          # PostgreSQL, Redis, bot, Celery worker
├── Dockerfile                  # Python 3.12-slim image
├── pyproject.toml              # Dependencies and tool config
├── alembic.ini                 # Alembic config
├── alembic/                    # Migration environment
│   ├── env.py
│   └── versions/
├── scripts/
│   └── seed_roles.py           # Seed admin/user roles + permissions
├── src/
│   ├── __main__.py             # Async entrypoint
│   ├── config.py               # pydantic-settings (all env vars)
│   ├── core/
│   │   ├── logging.py          # structlog + Rich + Telegram handler
│   │   └── i18n.py             # aiogram-i18n Fluent setup
│   ├── db/
│   │   ├── base.py             # DeclarativeBase
│   │   └── engine.py           # Async engine + session factory
│   ├── models/                 # SQLAlchemy 2.0 models
│   ├── repositories/           # Data access layer
│   ├── services/
│   │   ├── parser/             # Scraper, keyword matcher, report generator
│   │   └── ai/                 # OpenAI client with streaming
│   ├── bot/
│   │   ├── create.py           # Bot + Dispatcher factory
│   │   ├── middlewares/        # Auth, throttle, locale
│   │   ├── callbacks/          # Shared CallbackData classes
│   │   ├── keyboards/          # Shared inline keyboard builders
│   │   └── modules/            # Feature modules (each with handlers, callbacks, keyboards, services, states)
│   │       ├── start/          # /start command and main menu navigation
│   │       ├── profile/        # User profile and stats
│   │       ├── parsing/        # Parsing flow (FSM, detail, format export, key phrases)
│   │       ├── admin/          # Admin panel (users, settings, support)
│   │       └── user_settings/  # Language, blacklist, notifications, delete data
│   ├── worker/
│   │   ├── app.py              # Celery app
│   │   ├── circuit_breaker.py  # Redis-backed circuit breaker
│   │   ├── utils.py            # Shared task utilities
│   │   └── tasks/              # Parsing and AI tasks
│   └── locales/                # Fluent translation files (ru, en)
├── tests/
│   ├── conftest.py
│   ├── unit/                   # Scraper, extractor, keyword match, report, circuit breaker
│   └── integration/            # Bot handler tests
└── parser_script/              # Original CLI script (reference)
```

## Prerequisites

- **Python 3.12+**
- **Docker** and **Docker Compose** (for PostgreSQL and Redis, or for full deployment)
- A **Telegram bot token** from [@BotFather](https://t.me/BotFather)
- An **OpenAI API key** (or compatible endpoint)

---

## Local Development

### 1. Clone and configure

```bash
git clone <repo-url> hh_bot
cd hh_bot
cp .env.example .env
```

Edit `.env` with your values:

```dotenv
BOT_TOKEN=123456:ABC-your-bot-token
OPENAI_API_KEY=sk-your-key
ADMIN_TELEGRAM_IDS=your_telegram_user_id
```

### 2. Start infrastructure

Start PostgreSQL and Redis via Docker Compose (only the infra services):

```bash
docker compose up -d postgres redis
```

Verify they're healthy:

```bash
docker compose ps
```

### 3. Set up Python environment

```bash
python -m venv .venv

# Linux / macOS
source .venv/bin/activate

# Windows (PowerShell)
.venv\Scripts\Activate.ps1

pip install -e ".[dev]"
```

### 4. Run database migrations

```bash
alembic upgrade head
```

If no migrations exist yet (fresh clone), generate the initial migration first:

```bash
alembic revision --autogenerate -m "initial"
alembic upgrade head
```

### 5. Seed roles and permissions

```bash
python scripts/seed_roles.py
```

This creates `admin` and `user` roles with their respective permissions.

### 6. Start the bot

```bash
python -m src
```

### 7. Start the Celery worker (separate terminal)

```bash
celery -A src.worker.app worker --loglevel=info --concurrency=4
```

### 8. Run tests

```bash
pytest
pytest --cov=src       # with coverage
```

### 9. Lint

```bash
ruff check src/ tests/
ruff format src/ tests/
```

---

## Docker Compose (Full Stack)

To run everything in Docker (bot + worker + PostgreSQL + Redis):

```bash
cp .env.example .env
# Edit .env — set POSTGRES_HOST=postgres and REDIS_HOST=redis
# (these are the Docker service names, not localhost)

docker compose up -d --build
```

Important: when running inside Docker, the host values must match the service names:

```dotenv
POSTGRES_HOST=postgres
REDIS_HOST=redis
```

View logs:

```bash
docker compose logs -f bot
docker compose logs -f celery_worker
```

Run migrations inside the container:

```bash
docker compose exec bot alembic upgrade head
docker compose exec bot python scripts/seed_roles.py
```

---

## Deploying to Ubuntu Server

### 1. Server preparation

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y git curl ufw

# Install Docker
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER

# Install Docker Compose plugin (if not bundled)
sudo apt install -y docker-compose-plugin

# Log out and back in for group changes to take effect
```

### 2. Firewall

The bot uses long-polling (outbound only), so no inbound ports need to be opened for it. Lock down the server:

```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow ssh
sudo ufw enable
```

If you need to expose PostgreSQL or Redis externally (not recommended in production), open the specific ports.

### 3. Clone and configure

```bash
cd /opt
sudo mkdir hh_bot && sudo chown $USER:$USER hh_bot
git clone <repo-url> hh_bot
cd hh_bot

cp .env.example .env
nano .env
```

Set production values:

```dotenv
BOT_TOKEN=your-production-bot-token

POSTGRES_USER=hh_bot
POSTGRES_PASSWORD=<strong-random-password>
POSTGRES_DB=hh_bot
POSTGRES_HOST=postgres
POSTGRES_PORT=5432

REDIS_HOST=redis
REDIS_PORT=6379
REDIS_DB=0

OPENAI_API_KEY=sk-your-key
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4o-mini

LOG_LEVEL=INFO
LOG_TELEGRAM_CHAT_ID=<chat-id-for-error-alerts>
SUPPORT_CHAT_ID=<chat-id-for-support>

ADMIN_TELEGRAM_IDS=your_telegram_id
```

### 4. Build and start

```bash
docker compose up -d --build
```

### 5. Initialize the database

```bash
docker compose exec bot alembic upgrade head
docker compose exec bot python scripts/seed_roles.py
```

### 6. Verify

```bash
docker compose ps                    # all services should be "Up (healthy)"
docker compose logs -f bot           # check for "Bot is polling..."
docker compose logs -f celery_worker # check for "ready" message
```

Send `/start` to your bot in Telegram to confirm it's running.

### 7. Set up auto-restart on reboot

Docker Compose services are configured with `restart: unless-stopped`, so they will restart automatically after a server reboot as long as the Docker daemon starts on boot:

```bash
sudo systemctl enable docker
```

### 8. Updates

To deploy a new version:

```bash
cd /opt/hh_bot
git pull
docker compose up -d --build
docker compose exec bot alembic upgrade head   # if there are new migrations
```

### 9. Backups

Back up the PostgreSQL database regularly:

```bash
# Manual backup
docker compose exec postgres pg_dump -U hh_bot hh_bot > backup_$(date +%Y%m%d_%H%M%S).sql

# Restore
cat backup.sql | docker compose exec -T postgres psql -U hh_bot hh_bot
```

For automated backups, add a cron job:

```bash
crontab -e
```

```cron
0 3 * * * cd /opt/hh_bot && docker compose exec -T postgres pg_dump -U hh_bot hh_bot | gzip > /opt/hh_bot/backups/backup_$(date +\%Y\%m\%d).sql.gz
```

```bash
mkdir -p /opt/hh_bot/backups
```

---

## Environment Variables Reference

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `BOT_TOKEN` | Yes | — | Telegram bot token from BotFather |
| `POSTGRES_USER` | No | `hh_bot` | PostgreSQL username |
| `POSTGRES_PASSWORD` | No | `hh_bot_secret` | PostgreSQL password |
| `POSTGRES_DB` | No | `hh_bot` | PostgreSQL database name |
| `POSTGRES_HOST` | No | `localhost` | PostgreSQL host (`postgres` in Docker) |
| `POSTGRES_PORT` | No | `5432` | PostgreSQL port |
| `REDIS_HOST` | No | `localhost` | Redis host (`redis` in Docker) |
| `REDIS_PORT` | No | `6379` | Redis port |
| `REDIS_DB` | No | `0` | Redis database number |
| `OPENAI_API_KEY` | No | — | OpenAI API key |
| `OPENAI_BASE_URL` | No | `https://api.openai.com/v1` | OpenAI-compatible API endpoint |
| `OPENAI_MODEL` | No | `gpt-4o-mini` | Model to use for AI tasks |
| `LOG_LEVEL` | No | `INFO` | Logging level |
| `LOG_TELEGRAM_CHAT_ID` | No | — | Chat ID for ERROR+ log alerts |
| `SUPPORT_CHAT_ID` | No | — | Chat ID for support messages |
| `ADMIN_TELEGRAM_IDS` | No | — | Comma-separated Telegram user IDs for initial admin users |

## License

Private project. All rights reserved.
