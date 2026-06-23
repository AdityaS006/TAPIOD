"""
Step 2 of 2: Embed arena_prompts.json and upsert into Qdrant.
Run AFTER services are up (Qdrant must be reachable at localhost:6333).

Memory-safe: embeds in batches of 32 with gc.collect() between each batch.
Peak extra RAM: ~400 MB (BGE-small model + one batch).
"""
import gc
import json
import time
import uuid
from pathlib import Path

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams
from fastembed import TextEmbedding

BATCH_SIZE   = 32
EMBED_MODEL  = "BAAI/bge-small-en-v1.5"
COLLECTION   = "routing_examples"
QDRANT_URL   = "http://localhost:6333"
IN_FILE      = Path(__file__).parent / "arena_prompts.json"


def main():
    print(f"Loading prompts from {IN_FILE}…")
    data = json.loads(IN_FILE.read_text())
    texts  = [r["text"]  for r in data]
    labels = [r["label"] for r in data]
    print(f"  {len(texts):,} prompts  ({labels.count('fast')} fast / {labels.count('heavy')} heavy)")

    print(f"\nLoading embedding model ({EMBED_MODEL})…")
    model = TextEmbedding(model_name=EMBED_MODEL)

    print(f"Embedding in batches of {BATCH_SIZE} (low-memory mode)…")
    all_points = []

    for i in range(0, len(texts), BATCH_SIZE):
        batch_texts  = texts[i  : i + BATCH_SIZE]
        batch_labels = labels[i : i + BATCH_SIZE]

        vecs = [v.tolist() for v in model.embed(batch_texts)]

        for text, label, vec in zip(batch_texts, batch_labels, vecs):
            all_points.append(PointStruct(
                id=str(uuid.uuid4()),
                vector=vec,
                payload={"label": label, "text": text[:120], "source": "chatbot_arena"},
            ))

        gc.collect()

        done = min(i + BATCH_SIZE, len(texts))
        print(f"  embedded {done:,} / {len(texts):,}", end="\r", flush=True)
        time.sleep(0.05)   # tiny pause — keeps RAM stable

    print(f"\n  all {len(all_points):,} vectors ready")

    print(f"\nConnecting to Qdrant at {QDRANT_URL}…")
    qd = QdrantClient(url=QDRANT_URL)

    collections = [c.name for c in qd.get_collections().collections]
    if COLLECTION not in collections:
        print(f"Creating collection '{COLLECTION}'…")
        qd.create_collection(
            COLLECTION,
            vectors_config=VectorParams(size=384, distance=Distance.COSINE),
        )

    existing = qd.count(COLLECTION).count
    print(f"Clearing {existing} existing points…")
    if existing > 0:
        info = qd.get_collection(COLLECTION)
        vec_size = info.config.params.vectors.size
        qd.delete_collection(COLLECTION)
        qd.create_collection(COLLECTION, vectors_config=VectorParams(size=vec_size, distance=Distance.COSINE))

    print(f"Upserting {len(all_points):,} points in batches of {BATCH_SIZE}…")
    for i in range(0, len(all_points), BATCH_SIZE):
        batch = all_points[i : i + BATCH_SIZE]
        qd.upsert(collection_name=COLLECTION, points=batch)
        done = min(i + BATCH_SIZE, len(all_points))
        print(f"  upserted {done:,} / {len(all_points):,}", end="\r", flush=True)
        gc.collect()

    final = qd.count(COLLECTION).count
    print(f"\n✓ {COLLECTION} now has {final:,} points")
    print("Restart the gateway and run the benchmark.\n")


if __name__ == "__main__":
    main()
