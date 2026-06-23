  "use client";

import { useState, useEffect, useCallback } from "react";
import { Reorder } from "framer-motion";
import { Lock, GripVertical, CheckCircle, XCircle, Save, Trash2, ChevronRight } from "lucide-react";

const PROVIDERS = [
  { id: "anthropic", name: "Anthropic",     hint: "sk-ant-api03-..." },
  { id: "openai",    name: "OpenAI",         hint: "sk-proj-..." },
  { id: "groq",      name: "Groq",           hint: "gsk_..." },
  { id: "gemini",    name: "Google Gemini",  hint: "AIza..." },
];

const COMING_SOON_TOGGLE = ({ label }: { label: string }) => (
  <div className="flex items-center justify-between opacity-40 cursor-not-allowed">
    <span className="text-sm text-[var(--text-secondary)]">{label}</span>
    <div className="w-10 h-5 rounded-full bg-white/10 border border-white/10" />
  </div>
);

export default function Config() {
  const [tiers, setTiers]             = useState<any>(null);
  const [fastTier, setFastTier]       = useState<string[]>([]);
  const [heavyTier, setHeavyTier]     = useState<string[]>([]);
  const [keyStatuses, setKeyStatuses] = useState<{ provider: string; present: boolean }[]>([]);
  const [keyInputs, setKeyInputs]     = useState<Record<string, string>>({});
  const [saving, setSaving]           = useState<Record<string, boolean>>({});

  const fetchAll = useCallback(async () => {
    try {
      const [tiersRes, keysRes] = await Promise.all([
        fetch("/api/config/tiers"),
        fetch("/api/config/keys"),
      ]);
      if (tiersRes.ok) {
        const t = await tiersRes.json();
        setTiers(t);
        setFastTier(t.tiers?.fast ?? []);
        setHeavyTier(t.tiers?.heavy ?? []);
      }
      if (keysRes.ok) setKeyStatuses(await keysRes.json());
    } catch {}
  }, []);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  const saveKey = async (provider: string) => {
    const key = keyInputs[provider];
    if (!key) return;
    setSaving(s => ({ ...s, [provider]: true }));
    await fetch("/api/config/keys", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ provider, key }),
    });
    setKeyInputs(k => ({ ...k, [provider]: "" }));
    await fetchAll();
    setSaving(s => ({ ...s, [provider]: false }));
  };

  const deleteKey = async (provider: string) => {
    await fetch(`/api/config/keys/${provider}`, { method: "DELETE" });
    await fetchAll();
  };

  const handleReorder = async (tier: string, newOrder: string[]) => {
    if (tier === "fast") setFastTier(newOrder);
    else setHeavyTier(newOrder);
    await fetch("/api/config/tiers/reorder", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tier, order: newOrder }),
    });
  };

  const keyPresentFor = (alias: string): boolean => {
    const provider = alias.split("-")[1]; // "fast-groq" → "groq", "heavy-anthropic" → "anthropic"
    return keyStatuses.find(k => k.provider === provider)?.present ?? true;
  };

  const updateThreshold = async (key: string, value: number) => {
    await fetch("/api/config/thresholds", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ [key]: value }),
    });
    await fetchAll();
  };

  const SliderRow = ({
    label, configKey, min, max, step, unit,
  }: {
    label: string; configKey: string; min: number; max: number; step: number; unit: string;
  }) => {
    const val = tiers?.[configKey] ?? (configKey === "complexity_threshold" ? 0.5 : 0.85);
    return (
      <div className="flex items-center justify-between gap-6">
        <span className="text-sm text-[var(--text-secondary)] w-56">{label}</span>
        <div className="flex items-center gap-3 flex-1">
          <input
            type="range" min={min} max={max} step={step}
            defaultValue={val}
            className="flex-1 accent-[var(--accent-purple)]"
            onMouseUp={e => updateThreshold(configKey, parseFloat((e.target as HTMLInputElement).value))}
          />
          <span className="text-sm text-[var(--text-muted)] w-16 text-right">{val}{unit}</span>
        </div>
      </div>
    );
  };

  return (
    <div className="flex flex-col gap-8 pb-8">
      <div>
        <h1 className="text-[2.25rem] font-bold tracking-tight mb-2">Configuration</h1>
        <p className="text-[var(--text-muted)]">
          Manage API keys, model routing priority, cache settings, and guardrails.
        </p>
      </div>

      {/* API Keys */}
      <div className="glass-panel p-6 flex flex-col gap-4">
        <h2 className="text-sm font-semibold uppercase tracking-widest text-[var(--text-secondary)]">
          API Keys
        </h2>
        {PROVIDERS.map(({ id, name, hint }) => {
          const present = keyStatuses.find(k => k.provider === id)?.present ?? false;
          return (
            <div
              key={id}
              className="flex items-center gap-4 bg-white/5 rounded-lg p-3 border border-white/5"
            >
              <div className="flex items-center gap-2 w-40 shrink-0">
                {present
                  ? <CheckCircle size={14} className="text-[var(--accent-green)] shrink-0" />
                  : <XCircle    size={14} className="text-[var(--text-muted)]   shrink-0" />
                }
                <span className="text-sm font-medium text-[var(--text-primary)]">{name}</span>
              </div>
              <input
                type="password"
                placeholder={present ? "••••••••••••••••" : hint}
                value={keyInputs[id] ?? ""}
                onChange={e => setKeyInputs(k => ({ ...k, [id]: e.target.value }))}
                className="flex-1 bg-transparent border border-white/10 rounded-lg px-3 py-1.5 text-sm text-[var(--text-primary)] outline-none focus:border-[var(--accent-purple)]"
              />
              <button
                onClick={() => saveKey(id)}
                disabled={!keyInputs[id] || saving[id]}
                className="flex items-center gap-1 px-3 py-1.5 rounded-lg bg-[var(--accent-purple)] text-white text-xs disabled:opacity-30 shrink-0"
              >
                <Save size={12} /> Save
              </button>
              {present && (
                <button
                  onClick={() => deleteKey(id)}
                  className="text-[var(--text-muted)] hover:text-[var(--accent-red)] p-1 shrink-0"
                >
                  <Trash2 size={14} />
                </button>
              )}
            </div>
          );
        })}
        <p className="text-xs text-[var(--text-muted)] mt-1">
          Keys are stored encrypted in PostgreSQL. They are never shown after saving.
        </p>
      </div>

      {/* Model Priority */}
      <div className="glass-panel p-6 flex flex-col gap-6">
        <div>
          <h2 className="text-sm font-semibold uppercase tracking-widest text-[var(--text-secondary)]">
            Model Priority
          </h2>
          <p className="text-xs text-[var(--text-muted)] mt-1">
            Drag to reorder. TAPIOD uses the first available model in each tier.
            Greyed-out models are missing their API key.
          </p>
        </div>
        <div className="grid grid-cols-2 gap-6">
          {([
            { tier: "fast",  label: "Fast Tier",  values: fastTier,  caption: "complexity < threshold" },
            { tier: "heavy", label: "Heavy Tier", values: heavyTier, caption: "complexity ≥ threshold" },
          ] as const).map(({ tier, label, values, caption }) => (
            <div key={tier}>
              <h3 className="text-xs uppercase tracking-wider text-[var(--text-muted)] mb-3">
                {label} <span className="normal-case">({caption})</span>
              </h3>
              <Reorder.Group
                axis="y"
                values={values}
                onReorder={(newOrder) => handleReorder(tier, newOrder)}
                as="div"
                className="flex flex-col gap-2"
              >
                {values.map((alias: string, i: number) => {
                  const hasKey = keyPresentFor(alias);
                  return (
                    <Reorder.Item
                      key={alias}
                      value={alias}
                      as="div"
                      className="flex items-center gap-3 bg-white/5 rounded-lg p-3 border border-white/5 cursor-grab select-none"
                      style={{ opacity: hasKey ? 1 : 0.35 }}
                    >
                      <GripVertical size={14} className="text-[var(--text-muted)] shrink-0" />
                      <span className="text-xs text-[var(--text-muted)] w-4 shrink-0">{i + 1}</span>
                      <span className="flex-1 text-sm text-[var(--text-primary)]">{alias}</span>
                      {!hasKey && (
                        <span className="text-xs bg-white/10 rounded px-2 py-0.5 text-[var(--text-muted)] shrink-0">
                          No key
                        </span>
                      )}
                    </Reorder.Item>
                  );
                })}
              </Reorder.Group>
            </div>
          ))}
        </div>
      </div>

      {/* Fallback Behaviour */}
      <div className="glass-panel p-6 flex flex-col gap-4">
        <h2 className="text-sm font-semibold uppercase tracking-widest text-[var(--text-secondary)]">
          Fallback Behaviour
        </h2>
        <p className="text-sm text-[var(--text-muted)]">
          When a model fails (rate limit or quota exhausted), TAPIOD automatically
          tries the next model in your priority list.
        </p>
        <div className="flex flex-col gap-3 mt-1">
          {[
            { label: "Fast tier chain",  values: fastTier  },
            { label: "Heavy tier chain", values: heavyTier },
          ].map(({ label, values }) => (
            <div key={label} className="flex items-start gap-3">
              <span className="text-xs text-[var(--text-muted)] w-36 pt-0.5 shrink-0">{label}</span>
              <div className="flex items-center gap-1 flex-wrap">
                {values.length === 0 ? (
                  <span className="text-xs text-[var(--text-muted)]">—</span>
                ) : values.map((alias: string, i: number) => (
                  <span key={alias} className="flex items-center gap-1">
                    <span
                      className={`text-xs px-2 py-0.5 rounded ${
                        keyPresentFor(alias)
                          ? "bg-[var(--accent-purple)]/20 text-[var(--text-primary)]"
                          : "bg-white/5 text-[var(--text-muted)]"
                      }`}
                    >
                      {alias}
                    </span>
                    {i < values.length - 1 && (
                      <ChevronRight size={12} className="text-[var(--text-muted)]" />
                    )}
                  </span>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Thresholds */}
      <div className="glass-panel p-6 flex flex-col gap-5">
        <h2 className="text-sm font-semibold uppercase tracking-widest text-[var(--text-secondary)]">
          Thresholds
        </h2>
        <SliderRow
          label="KNN Routing threshold (fast vs heavy)"
          configKey="complexity_threshold"
          min={0.1} max={0.9} step={0.05} unit=""
        />
        <SliderRow
          label="Semantic cache similarity threshold"
          configKey="cache_similarity_threshold"
          min={0.5} max={0.99} step={0.01} unit=""
        />
        <SliderRow
          label="Redis cache TTL"
          configKey="cache_ttl_seconds"
          min={60} max={86400} step={60} unit="s"
        />
      </div>

      {/* Guardrails — Coming Soon */}
      <div className="glass-panel p-6 flex flex-col gap-4 opacity-70">
        <h2 className="text-sm font-semibold uppercase tracking-widest text-[var(--text-secondary)] flex items-center gap-2">
          <Lock size={14} /> Guardrails
          <span className="text-xs bg-white/10 rounded px-2 py-0.5 ml-1">Coming Soon</span>
        </h2>
        <COMING_SOON_TOGGLE label="Block harmful content" />
        <COMING_SOON_TOGGLE label="Max tokens per request" />
        <COMING_SOON_TOGGLE label="Rate limit per tenant" />
      </div>

      {/* PII Masking — Coming Soon */}
      <div className="glass-panel p-6 flex flex-col gap-4 opacity-70">
        <h2 className="text-sm font-semibold uppercase tracking-widest text-[var(--text-secondary)] flex items-center gap-2">
          <Lock size={14} /> PII Masking
          <span className="text-xs bg-white/10 rounded px-2 py-0.5 ml-1">Coming Soon</span>
        </h2>
        <COMING_SOON_TOGGLE label="Mask email addresses" />
        <COMING_SOON_TOGGLE label="Mask phone numbers" />
        <COMING_SOON_TOGGLE label="Mask credit card numbers" />
        <COMING_SOON_TOGGLE label="Restore PII in response" />
        <p className="text-xs text-[var(--text-muted)] mt-2">Powered by Microsoft Presidio</p>
      </div>
    </div>
  );
}
