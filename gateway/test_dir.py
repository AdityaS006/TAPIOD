import os
from routellm.controller import Controller

print("Testing dir(client)...")
client = Controller(
    routers=["mf"],
    strong_model="heavy-model",
    weak_model="fast-model"
)

print(dir(client))
