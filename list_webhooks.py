import requests
import os
from dotenv import load_dotenv

load_dotenv()

CLICKUP_TOKEN = os.getenv("CLICKUP_TOKEN")
TEAM_ID = os.getenv("TEAM_ID")

url = f"https://api.clickup.com/api/v2/team/{TEAM_ID}/webhook"
headers = {
    "Authorization": CLICKUP_TOKEN
}

res = requests.get(url, headers=headers)
webhooks = res.json().get("webhooks", [])

if not webhooks:
    print("✅ 没有任何 webhook")
else:
    print("✅ 现有 webhook：")
    for w in webhooks:
        print(f"ID: {w['id']}, endpoint: {w['endpoint']}, events: {w['events']}, list_id: {w.get('list_id')}")
