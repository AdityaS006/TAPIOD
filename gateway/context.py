import time
from dataclasses import dataclass, field


@dataclass
class RequestContext:
    prompt: str
    messages: list
    tenant_id: str
    user_id: str
    vec: list

    req_start: float = field(default_factory=time.perf_counter)

    cache_hit: bool = False
    cache_source: str = ""
    cache_saved_usd: float = 0.0

    injected_memories: list = field(default_factory=list)
    memory_tokens_saved: int = 0

    complexity_score: float = 0.0
    provider_model: str = ""
    routing_saved_usd: float = 0.0

    injected_tools: list = field(default_factory=list)

    actual_cost_usd: float = 0.0
    total_saved_usd: float = 0.0

    pipeline_trace: list = field(default_factory=list)

    def record(self, layer: str, result: str, latency_ms: float):
        self.pipeline_trace.append({
            "layer": layer,
            "result": result,
            "latency_ms": round(latency_ms, 2),
        })

    def compute_total_saved(self):
        self.total_saved_usd = self.cache_saved_usd + self.routing_saved_usd

    def to_trace_dict(self) -> dict:
        return {
            "pipeline": self.pipeline_trace,
            "actual_cost_usd": self.actual_cost_usd,
            "total_saved_usd": self.total_saved_usd,
            "cache_source": self.cache_source,
            "provider_model": self.provider_model,
            "injected_memories": self.injected_memories,
            "injected_tools": [t.get("function", {}).get("name") for t in self.injected_tools],
        }
