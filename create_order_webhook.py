# create_order_webhook.py
import os
import requests
from dotenv import load_dotenv

load_dotenv()

CLICKUP_TOKEN = os.getenv("CLICKUP_TOKEN")
TEAM_ID = os.getenv("TEAM_ID")

headers = {"Authorization": CLICKUP_TOKEN, "Content-Type": "application/json"}

# 只创建Order Record Webhook，指向同一个端点
order_webhook = {
    "endpoint": "https://clickup-webhook-server-xa5x.onrender.com/clickup-webhook",  # 注意：同一个端点！
    "events": ["taskUpdated"],
    "list_id": "901812062655"  # Order Record List ID
}

url = f"https://api.clickup.com/api/v2/team/{TEAM_ID}/webhook"

print("Creating Order Record Webhook...")
response = requests.post(url, headers=headers, json=order_webhook)
print(f"Order Webhook: {response.status_code} - {response.text}")
