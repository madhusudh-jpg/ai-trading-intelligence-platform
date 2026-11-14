# AI Trading Intelligence Platform

An analysis-only, multi-asset trading intelligence platform under development. The project is designed around provider-based market data ingestion, deterministic ICT (Inner Circle Trader) analysis, and evidence-based market intelligence.

**Execution mode:** Analysis only. The platform does not place broker orders or execute trades.

> **Project status:** Active development. Some backend capabilities are implemented and tested, while several product modules remain planned or are not yet integrated into a complete user workflow.

## 1. Project Scope

The intended market coverage includes:

- Forex
- Cryptocurrency
- US equities
- Indices
- NSE/BSE equities

Actual market availability depends on provider support, symbol mappings, API access, and data licensing. The currently implemented provider adapter in this repository is Binance, focused on cryptocurrency market data.

## 2. Architecture

The repository follows a modular monorepo structure.

| Directory | Responsibility | Current status |
|---|---|---|
| `apps/web` | Next.js and TypeScript web interface | Initial development interface |
| `apps/mobile` | React Native / Expo mobile client | Planned workspace |
| `services/api` | FastAPI backend, database models, market data and API routes | Implemented components |
| `services/ict-engine` | Independent deterministic ICT engine boundary | Architecture boundary documented; detection code currently resides in the API service |
| `services/ai-engine` | AI orchestration and explanation service | Planned boundary |
| `packages/contracts` | Shared API and schema contracts | Documentation scaffold |
| `docs` | Architecture decisions and development roadmap | Documentation |

### Backend technology

- Python 3.12+
- FastAPI
- Pydantic and Pydantic Settings
- SQLAlchemy
- Alembic
- PostgreSQL
- TimescaleDB
- Redis
- WebSockets
- Pytest and Ruff

### Web technology

- Next.js 15
- React 19
- TypeScript
- Tailwind CSS 4
- Lightweight Charts 5

## 3. Implemented Components

The following capabilities have corresponding implementation code in the repository.

### 3.1 Market Data Infrastructure

- Provider abstraction and provider registry
- Binance cryptocurrency provider adapter
- Historical candle retrieval
- WebSocket candle streaming
- Candle parsing and normalisation
- Candle ingestion and database persistence
- Candle completeness status
- Historical data recovery
- Gap detection
- Feed-health monitoring
- Provider status reporting
- Live ingestion worker with stream management and recovery logic
- Database retry handling for transient persistence failures

The Binance provider does not require an API key for the public market-data capabilities implemented in its adapter.

### 3.2 ICT Detection

The API service contains deterministic ICT detection schemas and service modules for:

- Swing detection
- Market structure
- Structure breaks
- Displacement
- Liquidity detection
- Imbalance and Fair Value Gap detection
- Order block detection
- Confluence analysis

The confluence service evaluates evidence and its relationships rather than simply counting every observation as independent evidence.

It supports directional alignment, conflicting evidence, neutral conditions, and insufficient evidence states.

**Important:** The detection services exist as Python modules. Their presence should not be interpreted as proof that a complete ICT analysis workflow is already exposed through the web interface or integrated into every API endpoint.

### 3.3 Database Layer

The API includes SQLAlchemy models and Alembic migrations for entities including:

- Users
- Instruments
- Provider symbol mappings
- Market candles
- ICT observations
- Analysis records
- AI analysis logs
- Trade setups
- Risk assessments
- Alerts
- Watchlists
- Trading journal records
- Backtesting records

The repository includes TimescaleDB-oriented candle storage migrations.

The presence of a model or migration does not mean its corresponding user-facing product feature is complete.

### 3.4 API Endpoints

The FastAPI application currently exposes these routes:

| Endpoint | Purpose |
|---|---|
| `GET /health` | API health check |
| `GET /api/v1/` | Platform overview and module statuses |
| `GET /api/v1/markets` | Supported market categories |
| `GET /api/v1/market-data/providers` | Provider status information |
| `GET /api/v1/instruments` | Search and list active instruments |
| `GET /api/v1/market-data/candles` | Retrieve stored candle data |
| `GET /api/v1/market-data/feeds` | Feed-health information |
| `GET /api/v1/market-data/feeds/{symbol}` | Feed-health information for a symbol |

Interactive API documentation is available through FastAPI's Swagger UI at `/docs` when the API is running.

## 4. Current Web Interface

The web application is an initial development interface.

It currently:

- Displays the platform name and development status.
- Retrieves the platform overview from the FastAPI backend.
- Displays supported market categories.
- Displays product module names and their reported statuses.
- Shows a backend connection error when the API is unavailable.
- Displays a notice that live market feeds and AI analysis are not enabled as complete product features.

It is not yet a complete interactive trading terminal with an integrated charting, ICT analysis, and AI copilot workflow.

## 5. Planned Product Modules

The following modules are part of the product roadmap. They must not be considered completed merely because they appear in the architecture or interface.

1. Trading terminal and charting
2. Market data integration across supported asset classes
3. Deterministic ICT analysis integration
4. Multi-timeframe analysis
5. AI copilot and evidence-grounded explanations
6. Trade setup generation
7. Risk management
8. Alerts and watchlists
9. Trading journal
10. Historical backtesting
11. Mobile application

See [`docs/roadmap.md`](docs/roadmap.md) for the staged implementation plan and [`docs/architecture.md`](docs/architecture.md) for the architecture decisions.

## 6. Prerequisites

To run the project locally, install:

- Windows 10/11, Linux, or macOS
- Docker Desktop with Docker Compose
- Python 3.12 or later
- Node.js 20 or later
- npm

## 7. Local Development Setup

Commands below use Windows PowerShell and assume the repository root is the current directory.

### Step 1: Configure environment variables

Create a local environment file from the example:

```powershell
Copy-Item .env.example .env
```

Review `.env` and configure the local database credentials.

Do not commit `.env` or publish API keys, passwords, or other secrets. The repository's `.gitignore` excludes `.env`.

### Step 2: Start PostgreSQL and Redis

From the repository root:

```powershell
docker compose up -d postgres redis
```

Check container status:

```powershell
docker compose ps
```

The Compose configuration provides:

- PostgreSQL/TimescaleDB on port `5432`
- Redis on port `6379`

### Step 3: Activate the Python environment

The virtual environment should be created at the repository root:

```powershell
python -m venv .venv
```

Activate it:

```powershell
.\.venv\Scripts\Activate.ps1
```

If PowerShell blocks script execution, use an appropriate local execution-policy setting or activate the environment from a terminal that permits it.

### Step 4: Install API dependencies

```powershell
cd services/api
pip install -e ".[dev]"
```

### Step 5: Apply database migrations

From `services/api`:

```powershell
alembic upgrade head
```

This applies the migration history to the configured database. Review the database URL before running migrations to ensure that it points to the intended local development database.

### Step 6: Start the FastAPI application

```powershell
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Open:

- API health: `http://localhost:8000/health`
- Swagger documentation: `http://localhost:8000/docs`

### Step 7: Start the web application

Open a second PowerShell terminal and return to the repository root:

```powershell
cd apps/web
npm install
npm run dev
```

Open:

`http://localhost:3000`

The web interface requests the backend overview from `http://127.0.0.1:8000/api/v1/`.

## 8. Market Data Configuration

Market-data settings are defined in:

`services/api/app/market_data/config.py`

The current configuration includes settings for:

- Binance
- Twelve Data
- Massive
- Historical backfill
- Live data
- Live ingestion
- Feed-health monitoring thresholds

For the Binance provider, the relevant environment settings include:

```dotenv
BINANCE_ENABLED=true
LIVE_DATA_ENABLED=true
LIVE_INGESTION_ENABLED=false
```

Live ingestion is disabled by default in the settings model. The application starts the live-ingestion worker only when Binance is enabled and both live-data and live-ingestion settings are enabled.

Enable live ingestion only after checking the instrument/provider mappings, database configuration, and feed requirements.

Other provider settings should only be enabled after the corresponding credentials and integrations have been configured and verified.

## 9. Testing and Code Quality

The backend test suite is located in:

`tests/`

It includes tests covering:

- API behaviour
- Database models
- Binance provider behaviour
- Candle ingestion
- PostgreSQL candle ingestion
- Feed-health monitoring
- Historical recovery
- Gap detection
- Live-ingestion worker behaviour
- Timeframe handling
- ICT schemas and detection services
- ICT confluence analysis

Run the test suite from `services/api`:

```powershell
python -m pytest ..\..\tests -v
```

Run Ruff:

```powershell
python -m ruff check .
```

Tests should be run against an appropriately configured test database where database integration is required. Do not use a production database for tests.

## 10. Design Principles

The architecture follows these principles:

- **Analysis only:** no broker order execution.
- **Deterministic detection:** ICT rules should be testable, versioned, and reproducible.
- **Evidence-grounded AI:** language models should explain validated evidence rather than invent market structure or price levels.
- **Provider-aware data:** market data must retain its source and provider context.
- **Time consistency:** UTC timestamps are used internally, with exchange/session timezone metadata retained where needed.
- **Data reliability:** candle completeness, feed freshness, recovery, and historical consistency are explicit concerns.
- **No look-ahead bias:** historical analysis should not silently use future information.

## 11. Repository Structure

```text
ai-trading-intelligence-platform/
│
├── apps/
│   ├── web/
│   │   └── Next.js web application
│   └── mobile/
│       └── Planned React Native / Expo workspace
│
├── services/
│   ├── api/
│   │   ├── app/
│   │   │   ├── api/
│   │   │   ├── core/
│   │   │   ├── db/
│   │   │   ├── ict_detection/
│   │   │   ├── market_data/
│   │   │   └── schemas/
│   │   ├── migrations/
│   │   ├── confluence_all_in_one.py
│   │   └── pyproject.toml
│   │
│   ├── ict-engine/
│   │   └── Service boundary documentation
│   │
│   └── ai-engine/
│       └── Service boundary documentation
│
├── packages/
│   └── contracts/
│
├── docs/
│   ├── architecture.md
│   └── roadmap.md
│
├── tests/
│
├── docker-compose.yml
├── .env.example
├── .gitignore
└── README.md
```

## 12. Development Status

This repository is under active development. Backend infrastructure, market-data components, database models and migrations, and ICT detection services have implementation code and associated tests.

The web interface is currently an initial status-oriented development page. The AI engine, mobile client, multi-asset provider coverage, and several end-user product workflows remain planned or require further integration and verification.

The project roadmap uses tested functionality and integration readiness—not the presence of a module name or interface—as release criteria.

---

**Repository:** [AI Trading Intelligence Platform](https://github.com/madhusudh-jpg/ai-trading-intelligence-platform)