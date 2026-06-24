"use client";

import { useState, useEffect } from "react";
import { TrendingDown, Zap, Brain, Activity } from "lucide-react";

interface Trace {
  id: number;
  timestamp: string;
  model: string;
  actual_cost_usd: number;
  total_saved_usd: number;
  cache_source: string | null;
  memory_tokens_saved: number;
  pipeline: { layer: string; result: string; latency_ms: number }[];
}

interface Savings {
  actual_cost_usd: number;
  total_saved_usd: number;
  baseline_usd: number;
  savings_pct: number;
  cache_saved_usd: number;
  routing_saved_usd: number;
  memory_tokens_saved: number;
  cache_hits_redis: number;
  cache_hits_qdrant: number;
}

const LAYER_LABELS: Record<string, string> = {
  redis_cache: "Redis L1",
  qdrant_cache: "Qdrant L2",
  memory_recall: "Memory",
  knn_router: "KNN Router",
  tool_select: "Tools",
  llm_call: "LLM",
  embed: "Embed",
};

export default function Dashboard() {
  const [savings, setSavings] = useState<Savings | null>(null);
  const [traces, setTraces] = useState<Trace[]>([]);
  const [metrics, setMetrics] = useState<any | null>(null);

  useEffect(() => {
    const fetchAll = async () => {
      try {
        const [sRes, tRes, mRes] = await Promise.all([
          fetch("/api/savings"),
          fetch("/api/traces?limit=10"),
          fetch("/api/metrics"),
        ]);
        if (sRes.ok) {
          const d = await sRes.json();
          if (!d.error) setSavings(d);
        }
        if (tRes.ok) { const d = await tRes.json(); setTraces(d.traces || []); }
        if (mRes.ok) {
          const d = await mRes.json();
          if (!d.error) setMetrics(d);
        }
      } catch {}
    };
    fetchAll();
    const interval = setInterval(fetchAll, 3000);
    return () => clearInterval(interval);
  }, []);

  const cacheHitRate = metrics
    ? (((metrics.cache_hits || 0) / Math.max(metrics.total_requests || 1, 1)) * 100).toFixed(1) + "%"
    : "—";

  return (
    <div className="flex flex-col h-full gap-6">
      <div className="flex items-end justify-between">
        <div>
          <h1 className="text-[2.25rem] font-bold tracking-tight mb-2">Cost Savings</h1>
          <p className="text-[var(--text-muted)]">Live view of what TAPIOD saves vs. direct API usage.</p>
        </div>
        <span className="flex items-center gap-2 text-[var(--accent-green)] text-sm font-medium">
          <span className="w-2 h-2 rounded-full bg-[var(--accent-green)] animate-pulse" />
          Live
        </span>
      </div>

      {/* KPI cards */}
      <div className="grid grid-cols-4 gap-4">
        {[
          {
            label: "Total Saved",
            value: savings ? `$${savings.total_saved_usd.toFixed(4)}` : "$—",
            sub: "vs. direct API",
            icon: TrendingDown,
            color: "var(--accent-green)",
          },
          {
            label: "Actual Spend",
            value: savings ? `$${savings.actual_cost_usd.toFixed(4)}` : "$—",
            sub: "charged by providers",
            icon: Activity,
            color: "var(--accent-purple-light)",
          },
          {
            label: "Cache Rate",
            value: cacheHitRate,
            sub: `Redis: ${savings?.cache_hits_redis ?? 0}  Qdrant: ${savings?.cache_hits_qdrant ?? 0}`,
            icon: Zap,
            color: "var(--accent-orange)",
          },
          {
            label: "Memory Recall",
            value: savings ? `${savings.memory_tokens_saved.toLocaleString()} tkns` : "—",
            sub: "saved by recall",
            icon: Brain,
            color: "var(--accent-blue-light)",
          },
        ].map(({ label, value, sub, icon: Icon, color }) => (
          <div key={label} className="glass-panel p-6 flex flex-col gap-3">
            <div className="flex items-center justify-between">
              <span className="text-[11px] uppercase tracking-widest text-[var(--text-muted)] font-medium">{label}</span>
              <Icon size={16} style={{ color }} strokeWidth={1.5} />
            </div>
            <div className="text-[2rem] font-bold leading-none" style={{ color }}>{value}</div>
            <div className="text-xs text-[var(--text-muted)]">{sub}</div>
          </div>
        ))}
      </div>

      {/* Savings breakdown */}
      {savings && (
        <div className="glass-panel p-6">
          <h3 className="text-sm font-semibold text-[var(--text-secondary)] mb-4 uppercase tracking-widest">Savings Breakdown</h3>
          <div className="grid grid-cols-3 gap-6">
            <div>
              <div className="text-xs text-[var(--text-muted)] mb-1">Cache hits</div>
              <div className="text-lg font-bold text-[var(--accent-green)]">${savings.cache_saved_usd.toFixed(4)}</div>
            </div>
            <div>
              <div className="text-xs text-[var(--text-muted)] mb-1">Smart routing</div>
              <div className="text-lg font-bold text-[var(--accent-orange)]">${savings.routing_saved_usd.toFixed(4)}</div>
            </div>
            <div>
              <div className="text-xs text-[var(--text-muted)] mb-1">vs. baseline (est.)</div>
              <div className="text-lg font-bold text-[var(--accent-purple-light)]">{savings.savings_pct}% reduction</div>
            </div>
          </div>
        </div>
      )}

      {/* Live trace feed */}
      <div className="glass-panel p-6 flex-1 flex flex-col">
        <h3 className="text-sm font-semibold text-[var(--text-secondary)] mb-4 uppercase tracking-widest">Live Request Traces</h3>
        <div className="flex flex-col gap-3 overflow-y-auto flex-1">
          {traces.length === 0 && (
            <p className="text-[var(--text-muted)] text-sm">No requests yet — send a message via the Playground.</p>
          )}
          {traces.map((t) => (
            <div key={t.id} className="bg-black/20 rounded-lg p-4 border border-white/5 font-mono text-xs">
              <div className="flex items-center justify-between mb-2">
                <span className="text-[var(--accent-purple-light)]">{t.timestamp}</span>
                <span className="flex items-center gap-3">
                  {t.cache_source && (
                    <span className="text-[var(--accent-green)] font-semibold">
                      {t.cache_source === "redis" ? "⚡ Redis HIT" : "🔷 Qdrant HIT"} — $0.00
                    </span>
                  )}
                  {!t.cache_source && (
                    <>
                      <span className="text-[var(--text-muted)]">{t.model}</span>
                      <span className="text-[var(--accent-red)]">cost ${t.actual_cost_usd.toFixed(6)}</span>
                      <span className="text-[var(--accent-green)]">saved ${t.total_saved_usd.toFixed(6)}</span>
                    </>
                  )}
                </span>
              </div>
              <div className="flex gap-2 flex-wrap">
                {t.pipeline.map((step, i) => (
                  <span key={i} className="bg-white/5 rounded px-2 py-0.5 text-[10px] text-[var(--text-secondary)]">
                    {LAYER_LABELS[step.layer] ?? step.layer}: {step.result}
                  </span>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
