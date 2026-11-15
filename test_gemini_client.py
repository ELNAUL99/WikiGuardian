import json

from app.agents.gemini_client import GeminiClient


print("INITIALIZING GEMINI CLIENT...")

gemini = GeminiClient()

print("GEMINI CLIENT INITIALIZATION: SUCCESS")
print("Configured model:", gemini.model)

prompt = """
Return a JSON object with exactly these fields:
{
    "status": "success",
    "provider": "Google Gemini",
    "project": "WikiGuardian",
    "message": "API connection verified"
}

Return JSON only.
"""

print("\nSENDING TEST REQUEST...")

response = gemini.generate(
    agent_name="integration_test",
    prompt=prompt,
)

data = json.loads(response)

assert data["status"] == "success"
assert data["provider"] == "Google Gemini"
assert data["project"] == "WikiGuardian"
assert data["message"] == "API connection verified"

print("GEMINI API REQUEST: SUCCESS")
print("JSON RESPONSE VALIDATION: SUCCESS")
print("\nResponse:")
print(json.dumps(data, indent=2))
