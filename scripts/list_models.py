import requests
import json

headers = {"Authorization": "Bearer REDACTED_GROQ_KEY"}
resp = requests.get("https://api.groq.com/openai/v1/models", headers=headers)
data = resp.json()

print(json.dumps([m["id"] for m in data.get("data", [])], indent=2))
