import requests
import os
from dotenv import load_dotenv

load_dotenv()

CLICKUP_TOKEN = os.getenv("CLICKUP_TOKEN")
WEBHOOK_ID = "d6890be3-ce65-46d3-b08c-c22d87ab4bc7"

url = f"https://api.clickup.com/api/v2/webhook/{WEBHOOK_ID}"
headers = {
    "Authorization": CLICKUP_TOKEN
}

res = requests.delete(url, headers=headers)
print(res.status_code)
print(res.text)
