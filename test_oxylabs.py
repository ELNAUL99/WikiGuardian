import os
from pathlib import Path

import requests
from dotenv import load_dotenv

env_file = Path(__file__).resolve().parent / ".env"

if not env_file.exists():
    raise FileNotFoundError(f".env file not found: {env_file}")

load_dotenv(
    dotenv_path=env_file,
    override=True,
    encoding="utf-8-sig",
)

api_key = os.getenv("OXYLABS_WEB_API_KEY", "").strip()

if not api_key:
    raise RuntimeError("Oxylabs API key is empty or missing.")

print("Environment file found:", True)
print("API key loaded:", True)
print("API key length:", len(api_key))

response = requests.post(
    "https://webapi.oxylabs.io/v1/search",
    headers={
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    },
    json={
        "query": "Helsinki Finland capital",
        "max_results": 3,
    },
    timeout=120,
)

print("\nHTTP status:", response.status_code)

if not response.ok:
    print("Oxylabs error response:")
    print(response.text[:2000])
    raise SystemExit("Oxylabs request failed.")

data = response.json()
results = data.get("results", [])

print("\nOXYLABS CONNECTION TEST: SUCCESS")
print("Results returned:", len(results))

for item in results:
    print("\nTitle:", item.get("title"))
    print("URL:", item.get("url"))
