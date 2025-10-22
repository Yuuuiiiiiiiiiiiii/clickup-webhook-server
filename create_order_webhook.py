# create_order_webhook.py - 修复版本
import os
import requests
from dotenv import load_dotenv

load_dotenv()

CLICKUP_TOKEN = os.getenv("CLICKUP_TOKEN")
TEAM_ID = os.getenv("TEAM_ID")

headers = {"Authorization": CLICKUP_TOKEN, "Content-Type": "application/json"}

# 删除可能存在的旧webhook
print("🔍 Checking for existing webhooks...")
url = f"https://api.clickup.com/api/v2/team/{TEAM_ID}/webhook"
response = requests.get(url, headers=headers)

if response.status_code == 200:
    webhooks = response.json().get("webhooks", [])
    for webhook in webhooks:
        if webhook.get("list_id") == "901812062655":
            webhook_id = webhook["id"]
            print(f"🗑️ Deleting old Order Record webhook: {webhook_id}")
            delete_url = f"https://api.clickup.com/api/v2/webhook/{webhook_id}"
            delete_response = requests.delete(delete_url, headers=headers)
            print(f"Delete response: {delete_response.status_code}")

# 创建新的Order Record Webhook，监听创建和更新事件
order_webhook = {
    "endpoint": "https://clickup-webhook-server-xa5x.onrender.com/clickup-webhook",
    "events": ["taskCreated", "taskUpdated"],  # 添加taskCreated事件
    "list_id": "901812062655"  # Order Record List ID
}

print("🆕 Creating new Order Record Webhook with taskCreated event...")
response = requests.post(url, headers=headers, json=order_webhook)
print(f"Order Webhook: {response.status_code} - {response.text}")