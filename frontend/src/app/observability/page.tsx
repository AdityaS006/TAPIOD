"use client";

import { useState, useEffect } from "react";
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer } from "recharts";

const COLORS = ["#a855f7", "#3b82f6", "#10b981", "#f59e0b", "#ef4444"];

function SavingsBar({ label, value, total, color }: { label: string; value: number; total: number; color: string }) {
  const pct = total > 0 ? (value / total) * 100 : 0;
  return (
    <div className="flex flex-col gap-1">
      <div className="flex justify-between text-xs">
        <span className="text-[var(--text-secondary)]">{label}</span>
        <span className="font-mono text-[var(--text-muted)]">${value.toFixed(6)}</span>
      </div>
      <div className="h-2 rounded-full bg-white/5 overflow-hidden">
        <div
          className="h-full rounded-full transition-all duration-700"
          style={{ width: `${pct}%`, background: color }}
        />
      </div>
    </div>
  );
}

export default function Observability() {
  const [stats, setStats] = useState<any | null>(null);
  const [savings, setSavings] = useState<any | null>(null);
  const [timeRange, setTimeRange] = useState("24h");

  useEffect(() => {
    const fetchAll = async () => {
      try {
        const [rRes, sRes] = await Promise.all([
          fetch(`/api/routing-stats?time_range=${timeRange}`),
          fetch(`/api/savings?time_range=${timeRange}`),
        ]);
        if (rRes.ok) setStats(await rRes.json());
        if (sRes.ok) setSavings(await sRes.json());
      } catch {}
    };
    fetchAll();
    const id = setInterval(fetchAll, 5000);
    return () => clearInterval(id);
  }, [timeRange]);

  const baseline = stats?.baseline_usd ?? 0;
  const actual = stats?.actual_usd ?? 0;
  const saved = stats?.arbitrage_saved_usd ?? 0;
  const savingsPct = baseline > 0 ? ((saved / baseline) * 100).toFixed(1) : "0";

  const totalSaved = savings?.total_saved_usd ?? 0;
  const cacheSaved = savings?.cache_saved_usd ?? 0;
  const routingSaved = savings?.routing_saved_usd ?? 0;
  const redisHits = savings?.cache_hits_redis ?? 0;
  const qdrantHits = savings?.cache_hits_qdrant ?? 0;
  const totalCacheHits = redisHits + qdrantHits;

  return (
    <div className="flex flex-col h-full gap-6">
      {/* Header */}
      <div className="flex items-end justify-between">
        <div>
          <h1 className="text-[2.25rem] font-bold tracking-tight mb-2">Provider Arbitrage</h1>
          <p className="text-[var(--text-muted)]">Real-time routing distribution and cost savings across all layers.</p>
        </div>
        <div className="flex gap-2">
          {["24h", "7d", "30d"].map(r => (
            <button
              key={r}
              onClick={() => setTimeRange(r)}
              className={`px-3 py-1 rounded-md text-sm border transition-all ${
                timeRange === r
                  ? "bg-[var(--accent-purple)] border-[var(--accent-purple)] text-white"
                  : "border-white/10 text-[var(--text-muted)] hover:border-white/20"
              }`}
            >
              {r}
            </button>
          ))}
        </div>
      </div>

      {/* Top stat cards */}
      <div className="grid grid-cols-4 gap-4">
        {[
          { label: "Baseline spend", value: `$${baseline.toFixed(4)}`, color: "var(--accent-red)", sub: "if every call hit the heavy model" },
          { label: "Actual spend", value: `$${actual.toFixed(4)}`, color: "var(--accent-green)", sub: "with TAPIOD optimisations" },
          { label: "Total saved", value: `${savingsPct}%`, color: "var(--accent-purple-light)", sub: `$${totalSaved.toFixed(4)} across ${timeRange}` },
          { label: "Cache hits", value: String(totalCacheHits), color: "var(--accent-blue)", sub: `${redisHits} Redis · ${qdrantHits} Qdrant` },
        ].map(({ label, value, color, sub }) => (
          <div key={label} className="glass-panel p-5 flex flex-col gap-2">
            <span className="text-[11px] uppercase tracking-widest text-[var(--text-muted)]">{label}</span>
            <span className="text-3xl font-bold" style={{ color }}>{value}</span>
            <span className="text-xs text-[var(--text-muted)]">{sub}</span>
          </div>
        ))}
      </div>

      {/* Middle row */}
      <div className="grid grid-cols-2 gap-6 flex-1">
        {/* Savings breakdown */}
        <div className="glass-panel p-6 flex flex-col gap-5">
          <h3 className="text-sm font-semibold uppercase tracking-widest text-[var(--text-secondary)]">Savings by Layer</h3>

          <div className="flex flex-col gap-4">
            <SavingsBar label="Semantic cache (Qdrant)" value={cacheSaved} total={totalSaved} color="#a855f7" />
            <SavingsBar label="Smart routing (model arbitrage)" value={routingSaved} total={totalSaved} color="#3b82f6" />
            <SavingsBar
              label="Exact-match cache (Redis)"
              value={Math.max(0, totalSaved - cacheSaved - routingSaved)}
              total={totalSaved}
              color="#10b981"
            />
          </div>

          <div className="mt-auto grid grid-cols-3 gap-3">
            {[
              { label: "Cache saved", value: `$${cacheSaved.toFixed(5)}`, color: "#a855f7" },
              { label: "Routing saved", value: `$${routingSaved.toFixed(5)}`, color: "#3b82f6" },
              { label: "Total saved", value: `$${totalSaved.toFixed(5)}`, color: "var(--accent-green)" },
            ].map(({ label, value, color }) => (
              <div key={label} className="bg-white/5 rounded-lg p-3 border border-white/5">
                <div className="text-[10px] text-[var(--text-muted)] mb-1">{label}</div>
                <div className="text-sm font-mono font-bold" style={{ color }}>{value}</div>
              </div>
            ))}
          </div>
        </div>

        {/* Routing distribution */}
        <div className="glass-panel p-6 flex flex-col">
          <h3 className="text-sm font-semibold uppercase tracking-widest text-[var(--text-secondary)] mb-4">Routing Distribution</h3>
          {stats?.distribution?.length > 0 ? (
            <>
              <ResponsiveContainer width="100%" height={180}>
                <PieChart>
                  <Pie data={stats.distribution} dataKey="count" nameKey="provider" cx="50%" cy="50%" outerRadius={75}>
                    {stats.distribution.map((_: unknown, i: number) => (
                      <Cell key={i} fill={COLORS[i % COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip formatter={(v: unknown) => `${v} requests`} />
                </PieChart>
              </ResponsiveContainer>
              <div className="flex flex-col gap-2 mt-4">
                {stats.distribution.map((d: unknown, i: number) => (
                  <div key={d.provider} className="flex items-center justify-between text-xs">
                    <span className="flex items-center gap-2">
                      <span className="w-2 h-2 rounded-full flex-shrink-0" style={{ background: COLORS[i % COLORS.length] }} />
                      <span className="truncate">{d.provider}</span>
                    </span>
                    <span className="text-[var(--text-muted)] flex-shrink-0 ml-2">{d.pct}% · ${d.cost.toFixed(4)}</span>
                  </div>
                ))}
              </div>
            </>
          ) : (
            <p className="text-[var(--text-muted)] text-sm">No routing data yet. Send a few requests to see the distribution.</p>
          )}
        </div>
      </div>

      {/* KNN info strip */}
      <div className="glass-panel p-5 flex items-center gap-8">
        <div className="flex-shrink-0">
          <div className="text-[10px] uppercase tracking-widest text-[var(--text-muted)] mb-1">KNN routing examples</div>
          <div className="text-2xl font-bold text-[var(--accent-purple-light)]">{stats?.routing_examples_count ?? 0}</div>
        </div>
        <div className="w-px h-10 bg-white/10 flex-shrink-0" />
        <p className="text-xs text-[var(--text-secondary)] leading-relaxed">
          Every prompt is embedded with <code className="text-[var(--accent-purple-light)]">BAAI/bge-small-en-v1.5</code> and matched against{" "}
          {stats?.routing_examples_count ?? 0} labeled arena prompts via KNN. Majority vote determines fast vs. heavy tier —
          no local ML model, just vector similarity. Cache checks run first and short-circuit the router entirely on hits.
        </p>
      </div>
    </div>
  );
}
