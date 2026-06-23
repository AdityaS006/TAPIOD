import os
from routellm.controller import Controller

print("Testing route method...")
client = Controller(
    routers=["mf"],
    strong_model="heavy-model",
    weak_model="fast-model"
)

try:
    prompt = "What is 2+2?"
    # The default threshold for cost optimization might be e.g. 0.5
    res = client.route(prompt, "mf", 0.5)
    print("Result of client.route(prompt):", type(res), res)
except Exception as e:
    print("Error:", e)
