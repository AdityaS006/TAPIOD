# TAPIOD Architecture

## Request Flow

```mermaid
flowchart TD
    Client["Client / Playground UI\n(port 3000)"]

    subgraph FastAPI ["FastAPI Gateway — port 4001"]
        AgentLoop["POST /api/agent/chat/completions\nMulti-turn agentic loop"]
        ToolExec["tool_executor.py\nexecute_tool()"]
    end

    subgraph LiteLLM ["LiteLLM Proxy — port 4000"]
        PreHook["async_pre_call_hook\n① inject system msg\n② embed prompt → Qdrant cache lookup\n③ RouteLLM model select\n④ embed prompt → tool injection"]
        PostHook["async_post_call_success_hook\n⑤ embed prompt → cache write\n⑥ zero out tokens on cache hit"]
        LogHook["async_log_success_event\n⑦ write to PostgreSQL"]
    end

    subgraph Infra ["Infrastructure (Docker)"]
        Qdrant["Qdrant :6333\ncollection: semantic_cache_384\ncollection: tool_registry\ncollection: routing_examples\ncollection: user_memory"]
        Postgres["PostgreSQL :5432\nrequests_log\nchat_sessions"]
        Redis["Redis :6379\nL1 exact-match cache"]
        Providers["LLM Providers\nGroq · OpenAI · Anthropic · Mistral\nfast-model / heavy-model per provider"]
    end

    Client -->|"1. POST /api/agent/chat/completions"| AgentLoop
    AgentLoop -->|"2. forward to LiteLLM"| PreHook
    PreHook -->|"cache lookup + tool lookup"| Qdrant
    PreHook -->|"route to fast or heavy"| Providers
    Providers -->|"response (or tool_calls)"| PostHook
    PostHook -->|"write response to cache"| Qdrant
    PostHook --> LogHook
    LogHook --> Postgres
    AgentLoop -->|"3. tool_calls detected"| ToolExec
    ToolExec -->|"4. real tool result"| AgentLoop
    AgentLoop -->|"5. second LLM call with result"| LiteLLM
```

---

## Latency Breakdown (per request, non-cached)

```mermaid
%%{init: {"theme": "base"}}%%
xychart-beta
    title "Overhead per request in milliseconds"
    x-axis ["Redis L1 lookup", "Qdrant cache lookup", "Embedding", "RouteLLM inference", "Tool lookup", "HTTP hop 4001→4000", "LLM provider call"]
    y-axis "ms" 0 --> 5000
    bar [0.1, 5, 9, 50, 5, 2, 1500]
```

> The semantic cache and smart routing are the primary cost-savers: a cache hit costs zero tokens and returns in ~5 ms; routing simple prompts to the fast model typically reduces token cost by 10×.

---

## Where the Layers Save Cost

```mermaid
flowchart LR
    subgraph Without ["Without TAPIOD (bare API)"]
        R1["Every request → heavy-model\n~$0.0009 / 1K tokens\n~1500ms latency"]
    end

    subgraph With ["With TAPIOD layers"]
        L1["L0: Redis exact match\n~0.1ms, $0"] --> L2
        L2["L1: Qdrant semantic cache\n~5ms, $0\n(hits: zero tokens charged)"] --> L3
        L3["L2: RouteLLM routing\nfast vs heavy\n~50ms overhead\nfast-model = 10× cheaper"] --> L4
        L4["L3: Dynamic tool injection\n~5ms\n(avoids hallucination cost)"] --> L5
        L5["L4: Multi-turn agent loop\nintercepts tool_calls\n(saves context window resubmission)"]
    end

    Without -.->|"each layer breaks even when\ncache hit rate > ~0.1%"| With
```

---

## Optimized Single-Embedding Architecture

The current implementation embeds the prompt once per hook invocation; the architecture below shows the target design where a single embedding vector is computed once and reused across all lookups in the same request.

```mermaid
sequenceDiagram
    participant C as Client
    participant GW as TAPIOD Gateway
    participant R as Redis (L1)
    participant Q as Qdrant (L2)
    participant E as Embed (once)
    participant LLM as LLM Provider

    C->>GW: POST /chat/completions

    GW->>R: exact-match key lookup (~0.1ms)
    alt Redis hit
        R-->>GW: cached response
        GW-->>C: return (0 tokens, ~0.5ms total)
    end

    GW->>E: embed prompt ONCE → vec
    E-->>GW: vec (384-dim)

    GW->>Q: semantic cache lookup (vec)
    alt Qdrant hit (score > 0.85)
        Q-->>GW: cached response
        GW->>R: backfill Redis with exact key
        GW-->>C: return (0 tokens, ~6ms total)
    end

    GW->>GW: route model (heuristic, ~0ms)
    GW->>Q: tool lookup (reuse same vec)
    Q-->>GW: relevant tools

    GW->>LLM: request with tools + routed model
    LLM-->>GW: response

    GW->>Q: cache write (reuse vec, async)
    GW->>R: cache write exact key (async)
    GW-->>C: return response
```

> **Single embedding per request.** Redis handles repeated identical prompts. Qdrant handles semantically similar ones. Cache writes are async and do not block the response.

---

## Qdrant Collections

| Collection | Dimensions | Purpose |
|---|---|---|
| `semantic_cache_384` | 384 | Cached LLM responses, keyed by prompt embedding |
| `tool_registry` | 384 | Tool definitions; top-3 injected per request by cosine similarity |
| `routing_examples` | 384 | 5,000 labelled prompts used for KNN-based fast/heavy routing |
| `user_memory` | 384 | Per-tenant persistent memory, injected into context |

---

## Infrastructure

| Service | Port | Role |
|---|---|---|
| Qdrant | 6333 / 6334 | Vector store — cache, tools, routing, memory |
| PostgreSQL | 5432 | Request logs and chat session storage |
| Redis | 6379 | L1 exact-match cache layer |
| LiteLLM Proxy | 4000 | Model routing, hooks, provider abstraction |
| FastAPI Gateway | 4001 | Agentic loop, tool execution, metrics API |
| Next.js Dashboard | 3000 | Live traces, observability, config UI |

**Supported LLM providers** (configured via the Config page or `routing_config.json`): Groq, OpenAI, Anthropic, Mistral. Provider priority and model-tier mapping are set at runtime — no code changes required to switch providers.
