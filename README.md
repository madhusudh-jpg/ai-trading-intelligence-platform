# AI Trading Intelligence Platform

A professional multi-asset charting and ICT-based market analysis platform. Initial scope: Forex, crypto, US equities, indices, and NSE/BSE equities. Analysis-only; no broker order execution.

## Architecture

- `apps/web`: Next.js + TypeScript web terminal
- `apps/mobile`: React Native / Expo application (planned workspace)
- `services/api`: FastAPI application and API contracts
- `services/ict-engine`: deterministic, versioned ICT detection service (module boundary)
- `services/ai-engine`: LLM orchestration and explanation service (module boundary)
- `packages/contracts`: shared API/schema documentation
- `infra`: local infrastructure
- `docs`: architecture and implementation decisions

## Start locally

Prerequisites: Docker Desktop, Node.js 20+, npm, Python 3.12+.

1. Copy `.env.example` to `.env` and set secrets.
2. Start infrastructure: `docker compose up -d postgres redis`
3. Start API: `cd services/api && python -m venv .venv && . .venv/bin/activate` (Windows: `.venv\\Scripts\\activate`), then `pip install -e .` and `uvicorn app.main:app --reload --port 8000`.
4. Start web: `cd apps/web && npm install && npm run dev`.

The initial scaffold deliberately does not fabricate live market data or AI signals. Provider integrations must be configured before displaying live prices.

## Product modules

1. Trading terminal and charting
2. Market data ingestion and normalisation
3. Deterministic ICT detection
4. Multi-timeframe analysis
5. AI copilot
6. Trade setup generation
7. Risk management
8. Alerts and watchlists
9. Trading journal
10. Historical backtesting

See `docs/architecture.md` and `docs/roadmap.md`.
