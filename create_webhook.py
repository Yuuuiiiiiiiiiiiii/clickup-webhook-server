import os
import requests
from dotenv import load_dotenv

load_dotenv()

CLICKUP_TOKEN = os.getenv("CLICKUP_TOKEN")
TEAM_ID = os.getenv("TEAM_ID")

headers = {"Authorization": CLICKUP_TOKEN, "Content-Type": "application/json"}

data = {
    "endpoint": "https://clickup-webhook-server-xa5x.onrender.com/clickup-webhook",  # 改成你的 Render URL
    "events": ["taskUpdated"],
}

url = f"https://api.clickup.com/api/v2/team/{TEAM_ID}/webhook"

response = requests.post(url, headers=headers, json=data)

print(response.status_code)
print(response.text)
