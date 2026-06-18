# TAPIOD Architecture & Cost Layer Analysis

## Current Request Flow

```mermaid
flowchart TD
    Client["🖥️ Client / Playground UI\n(port 3000)"]

    subgraph FastAPI ["FastAPI Gateway — port 4001"]
        AgentLoop["POST /api/agent/chat/completions\nMulti-turn agentic loop"]
        ToolExec["tool_executor.py\nexecute_tool()"]
    end

    subgraph LiteLLM ["LiteLLM Proxy — port 4000"]
        PreHook["async_pre_call_hook\n① inject system msg\n② embed prompt → Qdrant cache lookup\n③ RouteLLM model select\n④ embed prompt AGAIN → tool injection"]
        PostHook["async_post_call_success_hook\n⑤ embed prompt A THIRD TIME → cache write\n⑥ zero out tokens on cache hit"]
        LogHook["async_log_success_event\n⑦ write to PostgreSQL"]
    end

    subgraph Infra ["Infrastructure (Docker)"]
        Qdrant["🔷 Qdrant :6333\ncollection: semantic_cache_384\ncollection: tool_registry"]
        Postgres["🐘 PostgreSQL :5432\nrequests_log\nchat_sessions"]
        Redis["🔴 Redis :6379\n⚠️ UNUSED — wasted resource"]
        Groq["☁️ Groq API\nfast-model: llama-3.1-8b\nheavy-model: llama-3.3-70b"]
    end

    Client -->|"1. POST /api/agent/chat/completions"| AgentLoop
    AgentLoop -->|"2. forward to LiteLLM"| PreHook
    PreHook -->|"cache lookup + tool lookup"| Qdrant
    PreHook -->|"route to fast or heavy"| Groq
    Groq -->|"response (or tool_calls)"| PostHook
    PostHook -->|"write response to cache"| Qdrant
    PostHook --> LogHook
    LogHook --> Postgres
    AgentLoop -->|"3. tool_calls detected"| ToolExec
    ToolExec -->|"4. real tool result"| AgentLoop
    AgentLoop -->|"5. second LLM call with result"| LiteLLM
```

---

## Cost Per Layer (Current State)

```mermaid
%%{init: {"theme": "base"}}%%
xychart-beta
    title "Overhead per request (non-cached) in milliseconds"
    x-axis ["Redis exact match", "Qdrant cache lookup", "Embed × 3 (wasted)", "RouteLLM inference", "Tool lookup", "HTTP hop 4001→4000", "Groq API call"]
    y-axis "ms" 0 --> 5000
    bar [0, 5, 9, 50, 5, 2, 1500]
```

> **Key waste:** The prompt is embedded **3 separate times** per request — once for cache lookup, once for tool injection, and once again in the post-call hook for cache write.  
> **Redis is running but receives zero traffic.**

---

## Where the Layers Actually Save Cost

```mermaid
flowchart LR
    subgraph Without ["Without TAPIOD (bare API)"]
        R1["Every request → heavy-model\n~$0.0009 / 1K tokens\n~1500ms latency"]
    end

    subgraph With ["With TAPIOD layers"]
        L1["L0: Redis exact match\n⚡ ~0.1ms, $0"] --> L2
        L2["L1: Qdrant semantic cache\n⚡ ~5ms, $0\n(hits: zero tokens charged)"] --> L3
        L3["L2: RouteLLM routing\n🔀 fast vs heavy\n~50ms overhead\n💰 fast-model = 10× cheaper"] --> L4
        L4["L3: Dynamic tool injection\n🔧 ~5ms\n(avoids hallucination cost)"] --> L5
        L5["L4: Multi-turn agent loop\n🤖 intercepts tool_calls\n(saves context window resubmission)"]
    end

    Without -.->|"each layer breaks even when\ncache hit rate > ~0.1%"| With
```

---

## What's Missing to Compete

```mermaid
mindmap
  root((TAPIOD\nGaps))
    Cost Reduction
      Fix 3× embedding waste
      Activate Redis L1 cache
      Token compression / summarization
      Provider-level prefix caching
      Per-tenant budget guardrails
    Memory Layer
      Persistent user memory across sessions
      Workspace / project memory
      Memory retrieval → injects into context
      (compete with Supermemory)
    Multi-Provider
      OpenAI, Anthropic, Mistral fallback
      Cost-per-token routing
      (not just Groq)
    Observability
      Show $$$ saved per cache hit in dashboard
      Cost forecast / trend
      Per-tenant cost breakdown
    Developer Experience
      Single-port server (remove 4001→4000 hop)
      Fix Windows path hardcodes
      SDK / API key onboarding
```

---

## Proposed: Zero-Cost Overhead Architecture

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
        GW-->>C: ✅ return (0 tokens, ~0.5ms total)
    end

    GW->>E: embed prompt ONCE → vec
    E-->>GW: vec (384-dim)

    GW->>Q: semantic cache lookup (vec)
    alt Qdrant hit (score > 0.85)
        Q-->>GW: cached response
        GW->>R: backfill Redis with exact key
        GW-->>C: ✅ return (0 tokens, ~6ms total)
    end

    GW->>GW: route model (heuristic, ~0ms)
    GW->>Q: tool lookup (reuse same vec)
    Q-->>GW: relevant tools

    GW->>LLM: request with tools + routed model
    LLM-->>GW: response

    GW->>Q: cache write (reuse vec, async)
    GW->>R: cache write exact key (async)
    GW-->>C: ✅ return response
```

> **Single embedding per request.** Redis handles repeated identical prompts. Qdrant handles semantically similar ones. Cache writes are async and don't block the response.
