import os
from routellm.controller import Controller

# Use dummy keys for testing
os.environ["OPENAI_API_KEY"] = "sk-dummy"

print("Initializing Controller...")
# Use the matrix factorization router (fast, good performance)
# Strong model will be our 'heavy-model', weak model our 'fast-model'
client = Controller(
    routers=["mf"],
    strong_model="gpt-4o",
    weak_model="gpt-4o-mini"
)

prompts = [
    "What is the capital of France?",
    "Can you help me design a highly scalable microservice architecture using Kubernetes, Kafka, and Redis?"
]

for prompt in prompts:
    # RouteLLM routes based on prompt. We only care about WHICH model it chooses.
    # To get the routing decision without actually making the API call:
    print(f"\nPrompt: {prompt}")
    # Get the model it would route to
    route_result = client.router.get_route(prompt)
    model = client.strong_model if route_result >= 0.5 else client.weak_model
    print(f"Routed to: {model} (Score: {route_result})")
