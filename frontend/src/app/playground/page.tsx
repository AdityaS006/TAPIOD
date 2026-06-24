"use client";

import { useState, useRef, useEffect, useCallback } from "react";

interface PipelineStep {
  layer: string;
  result: string;
  latency_ms: number;
}

interface TapiodTrace {
  pipeline: PipelineStep[];
  actual_cost_usd: number;
  total_saved_usd: number;
  cache_source: string | null;
  provider_model: string;
  injected_memories: string[];
  injected_tools: string[];
}

interface Message {
  role: "user" | "assistant";
  content: string;
}

interface ChatSession {
  id: string;
  title: string;
  updatedAt: number;
  messages: Message[];
  tenant_id?: string;
  user_id?: string;
}

const USER_ID = "demo_user";
const TENANT_ID = "default_tenant";

const LAYER_ICONS: Record<string, string> = {
  embed: "🔢",
  redis_cache: "⚡",
  qdrant_cache: "🔷",
  memory_recall: "🧠",
  knn_router: "🔀",
  headroom: "🗜️",
  tool_select: "🔧",
  llm_call: "🤖",
};

const LAYER_LABELS: Record<string, string> = {
  embed: "Embed",
  redis_cache: "Redis L1",
  qdrant_cache: "Qdrant L2",
  memory_recall: "Memory",
  knn_router: "KNN Router",
  headroom: "Headroom",
  tool_select: "Tools",
  llm_call: "LLM Call",
};

export default function Playground() {
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [currentSessionId, setCurrentSessionId] = useState<string>(() => `session_${Date.now()}`);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [trace, setTrace] = useState<TapiodTrace | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  const fetchSessions = useCallback(async () => {
    try {
      const res = await fetch(`/api/chats?user_id=${USER_ID}&tenant_id=${TENANT_ID}`);
      if (res.ok) {
        const data = await res.json();
        if (Array.isArray(data)) setSessions(data);
      }
    } catch {}
  }, []);

  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => { fetchSessions(); }, [fetchSessions]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const saveSession = useCallback(async (id: string, msgs: Message[]) => {
    if (msgs.length === 0) return;
    const firstUser = msgs.find(m => m.role === "user")?.content ?? "Untitled";
    const title = firstUser.slice(0, 45) + (firstUser.length > 45 ? "…" : "");
    try {
      await fetch("/api/chats", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          id,
          title,
          updatedAt: Date.now(),
          messages: msgs,
          tenant_id: TENANT_ID,
          user_id: USER_ID,
        }),
      });
      fetchSessions();
    } catch {}
  }, [fetchSessions]);

  const loadSession = (session: ChatSession) => {
    setCurrentSessionId(session.id);
    setMessages(session.messages);
    setTrace(null);
    inputRef.current?.focus();
  };

  const newChat = () => {
    // eslint-disable-next-line react-hooks/purity
    setCurrentSessionId(`session_${Date.now()}`);
    setMessages([]);
    setTrace(null);
    inputRef.current?.focus();
  };

  const deleteSession = async (e: React.MouseEvent, id: string) => {
    e.stopPropagation();
    try {
      await fetch(`/api/chats/${id}?user_id=${USER_ID}&tenant_id=${TENANT_ID}`, { method: "DELETE" });
      setSessions(prev => prev.filter(s => s.id !== id));
      if (id === currentSessionId) newChat();
    } catch {}
  };

  const sendMessage = async () => {
    if (!input.trim() || loading) return;
    const userMsg: Message = { role: "user", content: input };
    const newMessages = [...messages, userMsg];
    setMessages(newMessages);
    setInput("");
    setLoading(true);
    setTrace(null);

    try {
      const res = await fetch("/api/agent/chat/completions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          model: "heavy-groq",
          messages: newMessages.map(m => ({ role: m.role, content: m.content })),
          user: USER_ID,
          metadata: { session_id: currentSessionId },
        }),
      });
      const data = await res.json();
      const content = data?.choices?.[0]?.message?.content ?? "No response.";
      const allMessages: Message[] = [...newMessages, { role: "assistant", content }];
      setMessages(allMessages);
      if (data._tapiod_trace) setTrace(data._tapiod_trace);
      await saveSession(currentSessionId, allMessages);
    } catch {
      setMessages(prev => [...prev, { role: "assistant", content: "Error reaching gateway." }]);
    } finally {
      setLoading(false);
    }
  };

  const formatTime = (ts: number) => {
    const d = new Date(ts);
    const now = new Date();
    const diffH = (now.getTime() - d.getTime()) / 3600000;
    if (diffH < 24) return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    return d.toLocaleDateString([], { month: "short", day: "numeric" });
  };

  return (
    <div className="flex h-full gap-4">
      {/* Sessions sidebar */}
      <div className="w-52 glass-panel p-4 flex flex-col gap-3 overflow-hidden">
        <div className="flex items-center justify-between">
          <span className="text-xs font-semibold uppercase tracking-widest text-[var(--text-secondary)]">Chats</span>
          <button
            onClick={newChat}
            className="text-[10px] px-2 py-1 rounded bg-[var(--accent-purple)]/20 text-[var(--accent-purple-light)] hover:bg-[var(--accent-purple)]/30 transition-colors"
          >
            + New
          </button>
        </div>
        <div className="flex-1 overflow-y-auto flex flex-col gap-1">
          {sessions.length === 0 && (
            <p className="text-[10px] text-[var(--text-muted)] mt-2">No saved chats yet.</p>
          )}
          {sessions.map(s => (
            <div
              key={s.id}
              onClick={() => loadSession(s)}
              className={`group flex flex-col gap-0.5 p-2 rounded-lg cursor-pointer transition-colors ${
                s.id === currentSessionId
                  ? "bg-[var(--accent-purple)]/20 border border-[var(--accent-purple)]/30"
                  : "hover:bg-white/5 border border-transparent"
              }`}
            >
              <div className="flex items-start justify-between gap-1">
                <span className="text-xs text-[var(--text-primary)] line-clamp-2 leading-tight flex-1">
                  {s.title}
                </span>
                <button
                  onClick={e => deleteSession(e, s.id)}
                  className="opacity-0 group-hover:opacity-100 text-[var(--text-muted)] hover:text-red-400 text-xs shrink-0 mt-0.5"
                >
                  ✕
                </button>
              </div>
              <span className="text-[10px] text-[var(--text-muted)]">{formatTime(s.updatedAt)}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Chat panel */}
      <div className="flex-1 flex flex-col glass-panel p-6">
        <h1 className="text-xl font-bold mb-4">Playground</h1>
        <div className="flex-1 overflow-y-auto flex flex-col gap-3 mb-4">
          {messages.length === 0 && (
            <p className="text-[var(--text-muted)] text-sm">
              Send a message. Watch the pipeline panel light up on the right.
            </p>
          )}
          {messages.map((m, i) => (
            <div key={i} className={`rounded-lg p-3 text-sm ${
              m.role === "user"
                ? "bg-[var(--accent-purple)]/10 border border-[var(--accent-purple)]/20 self-end max-w-[80%]"
                : "bg-white/5 border border-white/5 self-start max-w-[90%]"
            }`}>
              <p className="text-[10px] uppercase tracking-wider text-[var(--text-muted)] mb-1">
                {m.role === "user" ? "You" : "TAPIOD"}
              </p>
              <p className="text-[var(--text-primary)] whitespace-pre-wrap">{m.content}</p>
            </div>
          ))}
          {loading && (
            <div className="self-start bg-white/5 border border-white/5 rounded-lg p-3 text-sm text-[var(--text-muted)] animate-pulse">
              Processing through pipeline…
            </div>
          )}
          <div ref={bottomRef} />
        </div>
        <div className="flex gap-2">
          <input
            ref={inputRef}
            className="flex-1 bg-white/5 border border-white/10 rounded-lg px-4 py-2 text-sm text-[var(--text-primary)] outline-none focus:border-[var(--accent-purple-light)]"
            placeholder="Type a message…"
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => e.key === "Enter" && sendMessage()}
          />
          <button
            onClick={sendMessage}
            disabled={loading}
            className="px-4 py-2 rounded-lg bg-[var(--accent-purple)] text-white text-sm font-medium disabled:opacity-50"
          >
            Send
          </button>
        </div>
      </div>

      {/* Pipeline panel */}
      <div className="w-72 glass-panel p-6 flex flex-col gap-4 overflow-y-auto">
        <h2 className="text-sm font-semibold uppercase tracking-widest text-[var(--text-secondary)]">
          Pipeline
        </h2>

        {!trace && !loading && (
          <p className="text-[var(--text-muted)] text-xs">Pipeline trace will appear here after each request.</p>
        )}
        {loading && (
          <div className="flex flex-col gap-2">
            {["embed","redis_cache","qdrant_cache","memory_recall","knn_router","headroom","tool_select"].map(layer => (
              <div key={layer} className="flex items-center gap-2 opacity-40 animate-pulse">
                <span>{LAYER_ICONS[layer]}</span>
                <span className="text-xs text-[var(--text-muted)]">{LAYER_LABELS[layer]}…</span>
              </div>
            ))}
          </div>
        )}

        {trace && (
          <>
            <div className="flex flex-col gap-2">
              {trace.pipeline.map((step, i) => {
                const isHit = step.result.toLowerCase().includes("hit");
                const isMiss = step.result.toLowerCase().includes("miss");
                return (
                  <div
                    key={i}
                    className="flex flex-col gap-1 bg-white/5 rounded-lg p-2 border border-white/5"
                  >
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-medium flex items-center gap-1.5">
                        <span>{LAYER_ICONS[step.layer] ?? "•"}</span>
                        <span style={{ color: isHit ? "var(--accent-green)" : isMiss ? "var(--text-muted)" : "var(--text-primary)" }}>
                          {LAYER_LABELS[step.layer] ?? step.layer}
                        </span>
                      </span>
                      <span className="text-[10px] text-[var(--text-muted)]">{step.latency_ms.toFixed(1)}ms</span>
                    </div>
                    <span className="text-[10px] text-[var(--text-secondary)] pl-5">{step.result}</span>
                  </div>
                );
              })}
            </div>

            <div className="border-t border-white/5 pt-4 flex flex-col gap-2">
              <div className="flex justify-between text-xs">
                <span className="text-[var(--text-muted)]">Actual cost</span>
                <span className={trace.cache_source ? "text-[var(--accent-green)] font-bold" : "text-[var(--accent-red)]"}>
                  {trace.cache_source ? "$0.00" : `$${trace.actual_cost_usd.toFixed(6)}`}
                </span>
              </div>
              <div className="flex justify-between text-xs">
                <span className="text-[var(--text-muted)]">Saved (est.)</span>
                <span className="text-[var(--accent-green)]">${trace.total_saved_usd.toFixed(6)}</span>
              </div>
              {trace.provider_model && (
                <div className="flex justify-between text-xs">
                  <span className="text-[var(--text-muted)]">Provider</span>
                  <span className="text-[var(--accent-blue-light)]">{trace.provider_model}</span>
                </div>
              )}
            </div>

            {trace.injected_memories.length > 0 && (
              <div className="border-t border-white/5 pt-4">
                <p className="text-[10px] uppercase tracking-wider text-[var(--text-muted)] mb-2">Recalled memories</p>
                {trace.injected_memories.map((m, i) => (
                  <p key={i} className="text-xs text-[var(--text-secondary)] mb-1">📌 {m}</p>
                ))}
              </div>
            )}

            {trace.injected_tools.length > 0 && (
              <div className="border-t border-white/5 pt-4">
                <p className="text-[10px] uppercase tracking-wider text-[var(--text-muted)] mb-2">Tools injected</p>
                {trace.injected_tools.filter(Boolean).map((t, i) => (
                  <p key={i} className="text-xs text-[var(--text-secondary)] mb-1">🔧 {t}</p>
                ))}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
