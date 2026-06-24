"use client";

import { useState, useEffect } from "react";
import { Brain, Trash2 } from "lucide-react";

interface Memory {
  id: string;
  fact: string;
  timestamp: number;
  age: string;
}

export default function MemoryPage() {
  const [memories, setMemories] = useState<Memory[]>([]);
  const [loading, setLoading] = useState(true);
  const [wiping, setWiping] = useState(false);

  const userId = "demo_user";
  const tenantId = "default_tenant";

  const fetchMemories = async () => {
    try {
      const res = await fetch(
        `/api/memory?user_id=${userId}&tenant_id=${tenantId}`
      );
      if (res.ok) {
        const data = await res.json();
        setMemories(data.memories ?? []);
      }
    } catch {}
    setLoading(false);
  };

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    fetchMemories();
    const interval = setInterval(fetchMemories, 5000);
    return () => clearInterval(interval);
  }, []);

  const forgetOne = async (id: string) => {
    try {
      await fetch(`/api/memory/${id}`, { method: "DELETE" });
      setMemories(prev => prev.filter(m => m.id !== id));
    } catch {}
  };

  const wipeAll = async () => {
    if (!confirm("Wipe all stored memories for this user?")) return;
    setWiping(true);
    try {
      await fetch(
        `/api/memory?user_id=${userId}&tenant_id=${tenantId}`,
        { method: "DELETE" }
      );
      setMemories([]);
    } catch {}
    setWiping(false);
  };

  return (
    <div className="flex flex-col h-full gap-6">
      <div className="flex items-end justify-between">
        <div>
          <h1 className="text-[2.25rem] font-bold tracking-tight mb-2 flex items-center gap-3">
            <Brain size={32} strokeWidth={1.5} style={{ color: "var(--accent-blue-light)" }} />
            Memory
          </h1>
          <p className="text-[var(--text-muted)]">
            Facts TAPIOD has learned about you — recalled automatically to reduce tokens on future requests.
          </p>
        </div>
        <button
          onClick={wipeAll}
          disabled={wiping || memories.length === 0}
          className="flex items-center gap-2 px-4 py-2 rounded-lg border border-[var(--accent-red)]/30 text-[var(--accent-red)] text-sm hover:bg-[var(--accent-red)]/10 transition-colors disabled:opacity-30"
        >
          <Trash2 size={14} />
          Wipe all (GDPR)
        </button>
      </div>

      <div className="glass-panel p-6 flex-1 flex flex-col">
        <div className="flex items-center justify-between mb-4">
          <span className="text-[11px] uppercase tracking-widest text-[var(--text-muted)]">
            {memories.length} fact{memories.length !== 1 ? "s" : ""} stored
          </span>
          <span className="text-xs text-[var(--text-muted)]">user: {userId}</span>
        </div>

        {loading && (
          <p className="text-[var(--text-muted)] text-sm">Loading…</p>
        )}

        {!loading && memories.length === 0 && (
          <div className="flex-1 flex flex-col items-center justify-center gap-3 text-center">
            <Brain size={40} strokeWidth={1} style={{ color: "var(--text-muted)" }} />
            <p className="text-[var(--text-muted)] text-sm">
              No memories yet. Chat in the Playground and TAPIOD will start learning about you.
            </p>
          </div>
        )}

        <div className="flex flex-col gap-3 overflow-y-auto">
          {memories.map((m) => (
            <div
              key={m.id}
              className="flex items-center justify-between bg-white/5 rounded-lg p-4 border border-white/5 group"
            >
              <div className="flex items-start gap-3 flex-1 min-w-0">
                <span className="text-lg mt-0.5">📌</span>
                <div className="flex flex-col gap-1 min-w-0">
                  <p className="text-sm text-[var(--text-primary)] leading-snug">{m.fact}</p>
                  <p className="text-xs text-[var(--text-muted)]">{m.age}</p>
                </div>
              </div>
              <button
                onClick={() => forgetOne(m.id)}
                className="ml-4 p-2 rounded-lg text-[var(--text-muted)] hover:text-[var(--accent-red)] hover:bg-[var(--accent-red)]/10 transition-colors opacity-0 group-hover:opacity-100"
                title="Forget this"
              >
                <Trash2 size={14} />
              </button>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
