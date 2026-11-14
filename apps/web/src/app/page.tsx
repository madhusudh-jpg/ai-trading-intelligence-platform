
const moduleDetails: Record<string, { number: string; title: string; description: string }> = {
  trading_terminal: {
    number: "01",
    title: "Trading Terminal",
    description: "Charts, drawing tools and workspaces",
  },
  market_data: {
    number: "02",
    title: "Market Data",
    description: "Provider adapters and normalised feeds",
  },
  ict_detection: {
    number: "03",
    title: "ICT Detection",
    description: "Structure, liquidity, FVG and order blocks",
  },
  multi_timeframe_analysis: {
    number: "04",
    title: "Multi-Timeframe Analysis",
    description: "Higher- and lower-timeframe confluence",
  },
  ai_copilot: {
    number: "05",
    title: "AI Copilot",
    description: "Evidence-based market explanations",
  },
  trade_setup_generation: {
    number: "06",
    title: "Trade Setup Generator",
    description: "BUY / SELL / WAIT with entry, SL and TP",
  },
  risk_management: {
    number: "07",
    title: "Risk Management",
    description: "Position sizing and risk/reward",
  },
  alerts_and_watchlists: {
    number: "08",
    title: "Alerts & Watchlists",
    description: "Market conditions and setup notifications",
  },
  trading_journal: {
    number: "09",
    title: "Trading Journal",
    description: "Trade records and performance review",
  },
  backtesting: {
    number: "10",
    title: "Backtesting",
    description: "Historical strategy validation",
  },
};

interface PlatformModule {
  name: string;
  status: string;
}

interface PlatformOverview {
  name: string;
  supported_markets: string[];
  execution_mode: string;
  modules: PlatformModule[];
}

async function getPlatformOverview(): Promise<PlatformOverview | null> {
  try {
    const response = await fetch("http://127.0.0.1:8000/api/v1/", {
      cache: "no-store",
    });

    if (!response.ok) {
      return null;
    }

    return await response.json();
  } catch {
    return null;
  }
}

function formatStatus(status: string) {
  return status.replaceAll("_", " ");
}

export default async function Home() {
  const platform = await getPlatformOverview();

  return (
    <main className="min-h-screen p-6 md:p-10">
      <header className="mx-auto flex max-w-7xl items-center justify-between border-b border-[#252d38] pb-5">
        <div>
          <div className="text-xs font-semibold tracking-[.2em] text-violet-400">
            MARKET INTELLIGENCE
          </div>
          <h1 className="mt-1 text-xl font-semibold">Trading Workspace</h1>
        </div>

        <div className="rounded-full border border-[#34404e] px-3 py-1 text-xs text-slate-400">
          DEVELOPMENT
        </div>
      </header>

      <section className="mx-auto max-w-7xl py-10">
        <p className="text-sm text-slate-400">
          MULTI-ASSET · ICT ANALYSIS · AI ASSISTED
        </p>

        <h2 className="mt-3 max-w-3xl text-3xl font-semibold tracking-tight md:text-5xl">
          A unified workspace for professional market analysis.
        </h2>

        <p className="mt-4 max-w-2xl text-slate-400">
          {platform
            ? platform.supported_markets.join(", ").toUpperCase().replaceAll("_", "/")
            : "Forex, crypto, US stocks, indices and NSE/BSE"}
          . Analysis-only by design; all trade execution remains with the user.
        </p>

        {platform ? (
          <div className="mt-8 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {platform.modules.map((module) => {
              const details = moduleDetails[module.name];

              if (!details) return null;

              return (
                <article
                  key={module.name}
                  className="rounded-xl border border-[#252d38] bg-[#131820] p-5"
                >
                  <div className="text-xs text-violet-400">
                    MODULE {details.number}
                  </div>

                  <h3 className="mt-3 font-semibold">{details.title}</h3>

                  <p className="mt-2 text-sm text-slate-400">
                    {details.description}
                  </p>

                  <div className="mt-5 text-xs text-slate-500">
                    Status: {formatStatus(module.status)}
                  </div>
                </article>
              );
            })}
          </div>
        ) : (
          <div className="mt-8 rounded-xl border border-red-900/60 bg-red-950/20 p-4 text-sm text-red-200">
            Unable to connect to the backend. Check that the FastAPI server is running.
          </div>
        )}

        <div className="mt-8 rounded-xl border border-amber-900/60 bg-amber-950/20 p-4 text-sm text-amber-200">
          Live market feeds and AI analysis are not enabled yet. Connect
          licensed market data providers and configure AI credentials before
          showing live signals.
        </div>
      </section>
    </main>
  );
}
