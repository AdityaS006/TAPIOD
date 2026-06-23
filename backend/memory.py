import uuid
import time
from typing import Optional

from qdrant_client.models import Filter, FieldCondition, MatchValue


def memory_retrieve(
    qdrant,
    vec: list,
    user_id: str,
    tenant_id: str,
    top_k: int = 3,
    threshold: float = 0.7,
) -> list[str]:
    try:
        response = qdrant.query_points(
            collection_name="user_memory",
            query=vec,
            query_filter=Filter(
                must=[
                    FieldCondition(key="user_id", match=MatchValue(value=user_id)),
                    FieldCondition(key="tenant_id", match=MatchValue(value=tenant_id)),
                ]
            ),
            limit=top_k,
            score_threshold=threshold,
        )
        return [r.payload["fact"] for r in response.points if "fact" in r.payload]
    except Exception:
        return []


def build_memory_system_block(facts: list[str]) -> str:
    if not facts:
        return ""
    lines = "\n".join(f"- {f}" for f in facts)
    return f"\n\n[Recalled context about this user]\n{lines}"


def memory_store_fact(qdrant, embedding_model, user_id: str, tenant_id: str, fact: str):
    try:
        vec = list(embedding_model.embed([fact]))[0].tolist()
        qdrant.upsert(
            collection_name="user_memory",
            points=[{
                "id": str(uuid.uuid4()),
                "vector": vec,
                "payload": {
                    "user_id": user_id,
                    "tenant_id": tenant_id,
                    "fact": fact,
                    "timestamp": int(time.time()),
                },
            }],
        )
    except Exception:
        pass


EXTRACT_SYSTEM = (
    'Extract 0-3 concise facts about the user from this conversation turn. '
    'Return JSON only: {"facts": ["..."]}. '
    'Only extract stable, reusable facts about the user. '
    'Skip questions, one-off requests, or anything not about the user. '
    'If nothing durable, return {"facts": []}.'
)


async def memory_extract_and_store(
    qdrant, embedding_model, user_id: str, tenant_id: str,
    prompt: str, response_text: str, call_llm_fn
):
    import json
    messages = [
        {"role": "system", "content": EXTRACT_SYSTEM},
        {"role": "user", "content": f"User said: {prompt}\nAssistant replied: {response_text}"},
    ]
    try:
        raw = await call_llm_fn(messages, model="fast-groq")
        data = json.loads(raw)
        for fact in data.get("facts", []):
            if fact and fact.strip():
                memory_store_fact(qdrant, embedding_model, user_id, tenant_id, fact.strip())
    except Exception:
        pass
