# Architecture baseline

## Decisions
- Modular monorepo; web and mobile clients share backend contracts.
- FastAPI owns business logic and API boundaries.
- ICT detections are deterministic and versioned; LLMs explain evidence but do not invent price levels.
- Market data is provider-adapted and source-labelled. No universal consolidated feed is assumed.
- Analysis-only: no broker order placement endpoints in the initial product.

## Service boundaries
1. Trading terminal: chart presentation and workspace state.
2. Market data: provider adapters, normalisation, candle history and streaming.
3. ICT engine: structure, liquidity, imbalance and session detections.
4. Multi-timeframe analysis: timeframe aggregation and confluence.
5. AI copilot: grounded explanations over structured context.
6. Trade setup: deterministic validation and price/risk calculations.
7. Risk: instrument-aware sizing and exposure calculations.
8. Alerts/watchlists: user rules and event delivery.
9. Journal: user-entered trade records and outcomes.
10. Backtesting: reproducible historical simulation using versioned rules.

## Reliability principles
- UTC timestamps internally; retain exchange/session timezone metadata.
- Explicit candle completeness and feed freshness states.
- No look-ahead bias or silent historical repainting.
- Every detection records rule version, source candle range and lifecycle.
- Every AI analysis records its input context and model/version metadata.
