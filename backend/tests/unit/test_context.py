import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from context import RequestContext

def test_record_appends_to_trace():
    ctx = RequestContext(
        prompt="hello", messages=[], tenant_id="t1", user_id="u1", vec=[0.1, 0.2]
    )
    ctx.record("redis_cache", "miss", 0.1)
    assert len(ctx.pipeline_trace) == 1
    assert ctx.pipeline_trace[0]["layer"] == "redis_cache"
    assert ctx.pipeline_trace[0]["result"] == "miss"
    assert ctx.pipeline_trace[0]["latency_ms"] == 0.1

def test_record_rounds_latency():
    ctx = RequestContext(
        prompt="hi", messages=[], tenant_id="t1", user_id="u1", vec=[]
    )
    ctx.record("llm_call", "success", 842.1234567)
    assert ctx.pipeline_trace[0]["latency_ms"] == 842.12

def test_total_saved_sums_layers():
    ctx = RequestContext(
        prompt="x", messages=[], tenant_id="t1", user_id="u1", vec=[]
    )
    ctx.cache_saved_usd = 0.05
    ctx.routing_saved_usd = 0.02
    ctx.compute_total_saved()
    assert abs(ctx.total_saved_usd - 0.07) < 1e-9
