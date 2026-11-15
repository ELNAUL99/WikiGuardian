from app.agents.gemini_client import GeminiClient

gemini = GeminiClient()

print("AVAILABLE GEMINI GENERATION MODELS")
print("=" * 55)

count = 0

for model in gemini.client.models.list():
    actions = getattr(model, "supported_actions", None) or []

    if "generateContent" in actions:
        print(model.name)
        count += 1

print("=" * 55)
print("Generation models found:", count)
