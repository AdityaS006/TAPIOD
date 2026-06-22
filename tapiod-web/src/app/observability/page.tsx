"use client";

import { useState, useEffect } from "react";
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer } from "recharts";

const COLORS = ["#a855f7", "#3b82f6", "#10b981", "#f59e0b", "#ef4444"];

export default function Observability() {
  const [stats, setStats] = useState<any>(null);
  const [timeRange, setTimeRange] = useState("24h");

  useEffect(() => {
    const fetchStats = async () => {
      try {
        const res = await fetch(`/api/routing-stats?time_range=${timeRange}`);
        if (res.ok) setStats(await res.json());
      } catch {}
    };
    fetchStats();
    const interval = setInterval(fetchStats, 5000);
    return () => clearInterval(interval);
  }, [timeRange]);

  const baseline = stats?.baseline_usd ?? 0;
  const actual = stats?.actual_usd ?? 0;
  const saved = stats?.arbitrage_saved_usd ?? 0;
  const savingsPct = baseline > 0 ? ((saved / baseline) * 100).toFixed(1) : "0";

  return (
    <div className="flex flex-col h-full gap-6">
      <div className="flex items-end justify-between">
        <div>
          <h1 className="text-[2.25rem] font-bold tracking-tight mb-2">Provider Arbitrage</h1>
          <p className="text-[var(--text-muted)]">Real-time routing distribution and cost comparison across providers.</p>
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

      <div className="grid grid-cols-3 gap-4">
        {[
          { label: "Baseline (worst case)", value: `$${baseline.toFixed(4)}`, color: "var(--accent-red)", sub: "all → most expensive provider" },
          { label: "Actual spend", value: `$${actual.toFixed(4)}`, color: "var(--accent-green)", sub: "with TAPIOD routing" },
          { label: "Arbitrage saved", value: `${savingsPct}%`, color: "var(--accent-purple-light)", sub: `$${saved.toFixed(4)} saved` },
        ].map(({ label, value, color, sub }) => (
          <div key={label} className="glass-panel p-6 flex flex-col gap-2">
            <span className="text-[11px] uppercase tracking-widest text-[var(--text-muted)]">{label}</span>
            <span className="text-3xl font-bold" style={{ color }}>{value}</span>
            <span className="text-xs text-[var(--text-muted)]">{sub}</span>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-2 gap-6 flex-1">
        <div className="glass-panel p-6 flex flex-col">
          <h3 className="text-sm font-semibold uppercase tracking-widest text-[var(--text-secondary)] mb-4">Routing Distribution</h3>
          {stats?.distribution?.length > 0 ? (
            <>
              <ResponsiveContainer width="100%" height={200}>
                <PieChart>
                  <Pie data={stats.distribution} dataKey="count" nameKey="provider" cx="50%" cy="50%" outerRadius={80}>
                    {stats.distribution.map((_: any, i: number) => (
                      <Cell key={i} fill={COLORS[i % COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip formatter={(v: any) => `${v} requests`} />
                </PieChart>
              </ResponsiveContainer>
              <div className="flex flex-col gap-2 mt-4">
                {stats.distribution.map((d: any, i: number) => (
                  <div key={d.provider} className="flex items-center justify-between text-xs">
                    <span className="flex items-center gap-2">
                      <span className="w-2 h-2 rounded-full" style={{ background: COLORS[i % COLORS.length] }} />
                      {d.provider}
                    </span>
                    <span className="text-[var(--text-muted)]">{d.pct}% · ${d.cost.toFixed(4)}</span>
                  </div>
                ))}
              </div>
            </>
          ) : (
            <p className="text-[var(--text-muted)] text-sm">No routing data yet.</p>
          )}
        </div>

        <div className="glass-panel p-6 flex flex-col gap-4">
          <h3 className="text-sm font-semibold uppercase tracking-widest text-[var(--text-secondary)]">KNN Classifier</h3>
          <div className="flex flex-col gap-3">
            <div className="bg-white/5 rounded-lg p-4 border border-white/5">
              <div className="text-xs text-[var(--text-muted)] mb-1">Training examples in Qdrant</div>
              <div className="text-2xl font-bold text-[var(--accent-purple-light)]">
                {stats?.routing_examples_count ?? 0}
              </div>
            </div>
            <div className="bg-white/5 rounded-lg p-4 border border-white/5">
              <div className="text-xs text-[var(--text-muted)] mb-2">How it works</div>
              <p className="text-xs text-[var(--text-secondary)] leading-relaxed">
                Every prompt is embedded with BAAI/bge-small-en-v1.5 and matched against{" "}
                {stats?.routing_examples_count ?? 0} labeled examples via KNN. Majority vote
                determines fast vs. heavy tier. No local ML model — just vector similarity.
              </p>
            </div>
            <div className="bg-white/5 rounded-lg p-4 border border-white/5">
              <div className="text-xs text-[var(--text-muted)] mb-1">Self-improving</div>
              <p className="text-xs text-[var(--text-secondary)]">
                When a fast-tier response fails, the prompt is automatically added as a heavy example,
                improving accuracy on future similar prompts.
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
