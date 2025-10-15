import requests
import os
from dotenv import load_dotenv

load_dotenv()

CLICKUP_TOKEN = os.getenv("CLICKUP_TOKEN")
WEBHOOK_ID = "b267eda9-d190-407a-9864-742afe9ebb5f"

url = f"https://api.clickup.com/api/v2/webhook/{WEBHOOK_ID}"
headers = {
    "Authorization": CLICKUP_TOKEN
}

res = requests.delete(url, headers=headers)
print(res.status_code)
print(res.text)
