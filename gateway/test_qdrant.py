from qdrant_client import QdrantClient
client = QdrantClient(url='http://localhost:6333')
points, _ = client.scroll('semantic_cache_1536', limit=5)
for p in points:
    print(f'Tenant: {p.payload["tenant_id"]}')
    
res = client.search('semantic_cache_1536', query_vector=points[0].vector, limit=2)
print('Search with identical vector:')
for r in res:
    print(f'Score: {r.score}, Tenant: {r.payload["tenant_id"]}')
