# check_webhooks.py
import os
import requests
from dotenv import load_dotenv

load_dotenv()

CLICKUP_TOKEN = os.getenv("CLICKUP_TOKEN")
TEAM_ID = os.getenv("TEAM_ID")

headers = {"Authorization": CLICKUP_TOKEN}
url = f"https://api.clickup.com/api/v2/team/{TEAM_ID}/webhook"

print("🔍 Checking current webhooks...")
response = requests.get(url, headers=headers)

if response.status_code == 200:
    webhooks = response.json().get("webhooks", [])
    print(f"📋 Found {len(webhooks)} webhooks:")
    
    for webhook in webhooks:
        print(f"ID: {webhook['id']}")
        print(f"Endpoint: {webhook['endpoint']}")
        print(f"List ID: {webhook.get('list_id', 'None')}")
        print(f"Events: {webhook['events']}")
        print(f"Status: {webhook.get('status', 'Unknown')}")
        print("-" * 50)
else:
    print(f"❌ Failed to get webhooks: {response.status_code} - {response.text}")
    