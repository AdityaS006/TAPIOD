import hashlib
import json
import time
from typing import Optional

from qdrant_client.models import Filter, FieldCondition, MatchValue


def redis_cache_key(tenant_id: str, messages: list) -> str:
    payload = json.dumps(
        {"tenant_id": tenant_id, "messages": messages},
        sort_keys=True,
    )
    return f"tapiod:cache:{hashlib.sha256(payload.encode()).hexdigest()}"


def redis_get(redis_client, tenant_id: str, messages: list) -> Optional[str]:
    try:
        key = redis_cache_key(tenant_id, messages)
        return redis_client.get(key)
    except Exception:
        return None


def redis_set(redis_client, tenant_id: str, messages: list,
              response_json: str, ttl: int = 3600):
    try:
        key = redis_cache_key(tenant_id, messages)
        redis_client.setex(key, ttl, response_json)
    except Exception:
        pass


def qdrant_cache_get(qdrant, vec: list, tenant_id: str, threshold: float = 0.85) -> Optional[str]:
    try:
        response = qdrant.query_points(
            collection_name="semantic_cache_384",
            query=vec,
            query_filter=Filter(
                must=[FieldCondition(key="tenant_id", match=MatchValue(value=tenant_id))]
            ),
            limit=1,
        )
        points = response.points
        if points and points[0].score > threshold:
            return points[0].payload.get("response")
    except Exception:
        pass
    return None


def qdrant_cache_set(qdrant, vec: list, tenant_id: str, prompt: str, response_text: str):
    import uuid
    try:
        qdrant.upsert(
            collection_name="semantic_cache_384",
            points=[{
                "id": str(uuid.uuid4()),
                "vector": vec,
                "payload": {
                    "tenant_id": tenant_id,
                    "prompt": prompt,
                    "response": response_text,
                    "timestamp": int(time.time()),
                },
            }],
        )
    except Exception:
        pass
