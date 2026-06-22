"""
One-time script. Run AFTER the gateway has started (so Qdrant is up and
the routing_examples collection exists).

Usage:
  cd gateway && source venv/bin/activate && python seed_routing.py
"""
import uuid
from qdrant_client import QdrantClient
from fastembed import TextEmbedding

FAST_EXAMPLES = [
    "What is the capital of France?",
    "Translate 'good morning' to Spanish.",
    "What's 15% of 80?",
    "Who wrote Romeo and Juliet?",
    "What does HTTP stand for?",
    "Convert 100 Fahrenheit to Celsius.",
    "What year did World War II end?",
    "Summarize this in one sentence: The sky is blue.",
    "What is the boiling point of water?",
    "Define the word 'ephemeral'.",
    "What is 2 to the power of 10?",
    "What language is spoken in Brazil?",
    "Give me a synonym for 'happy'.",
    "What time zone is Tokyo in?",
    "What is the currency of Japan?",
    "How many days are in a leap year?",
    "What does DNA stand for?",
    "What is the speed of light?",
    "Name three primary colors.",
    "What is the largest planet in our solar system?",
    "What does PDF stand for?",
    "Who invented the telephone?",
    "What is the square root of 144?",
    "What does RAM stand for in computing?",
    "How many continents are there?",
]

HEAVY_EXAMPLES = [
    "Write a comprehensive analysis of the pros and cons of microservices architecture versus monolithic design.",
    "Debug this Python async code and explain what's wrong with the event loop handling.",
    "Design a scalable database schema for a multi-tenant SaaS application with billing.",
    "Explain the mathematical intuition behind transformer attention mechanisms.",
    "Write a production-ready FastAPI authentication middleware with JWT and refresh tokens.",
    "Compare and contrast React, Vue, and Svelte for a large enterprise application.",
    "Analyze the trade-offs between eventual consistency and strong consistency in distributed systems.",
    "Write a technical blog post explaining how vector databases enable semantic search.",
    "Design a CI/CD pipeline for a microservices application deployed on Kubernetes.",
    "Explain how to implement a memory-efficient LRU cache in Python with O(1) operations.",
    "What are the security implications of storing JWTs in localStorage vs httpOnly cookies?",
    "Write a Redis-backed rate limiter for a high-traffic API in Python.",
    "Explain the CAP theorem and give a real-world example of each trade-off.",
    "How do I implement semantic search with embeddings and cosine similarity from scratch?",
    "Design an event-driven architecture for an e-commerce order processing system.",
    "Write a technical explanation of how LLM context windows work and their limitations.",
    "Analyze the performance characteristics of B-tree vs LSM-tree storage engines.",
    "How would you architect a real-time collaborative editing system like Google Docs?",
    "Explain gradient descent, backpropagation, and why vanishing gradients are a problem.",
    "Write a production monitoring strategy for a machine learning model in production.",
    "What are the trade-offs of using GraphQL versus REST for a public API?",
    "Implement a distributed lock using Redis and explain the failure modes.",
    "How do I optimize a slow PostgreSQL query with nested subqueries and large joins?",
    "Explain the differences between mutex, semaphore, and monitor in concurrent programming.",
    "Write a detailed plan for migrating a monolith to microservices without downtime.",
]


def seed():
    print("Connecting to Qdrant...")
    qdrant = QdrantClient(url="http://localhost:6333")

    existing = qdrant.count("routing_examples").count
    if existing > 0:
        print(f"routing_examples already has {existing} points. Skipping seed.")
        print("To re-seed, delete the collection first.")
        return

    print("Loading embedding model...")
    model = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")

    all_examples = (
        [(p, "fast") for p in FAST_EXAMPLES] +
        [(p, "heavy") for p in HEAVY_EXAMPLES]
    )

    prompts = [e[0] for e in all_examples]
    labels = [e[1] for e in all_examples]

    print(f"Embedding {len(prompts)} examples...")
    vecs = [v.tolist() for v in model.embed(prompts)]

    points = [
        {
            "id": str(uuid.uuid4()),
            "vector": vecs[i],
            "payload": {
                "label": labels[i],
                "prompt": prompts[i],
                "source": "seed",
            },
        }
        for i in range(len(prompts))
    ]

    qdrant.upsert(collection_name="routing_examples", points=points)
    print(f"Seeded {len(points)} routing examples ({len(FAST_EXAMPLES)} fast, {len(HEAVY_EXAMPLES)} heavy).")


if __name__ == "__main__":
    seed()
