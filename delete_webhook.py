import requests
import os
from dotenv import load_dotenv

load_dotenv()

CLICKUP_TOKEN = os.getenv("CLICKUP_TOKEN")
WEBHOOK_ID = "9da944d4-27fa-49d8-8e15-6f68cfa4151e"

url = f"https://api.clickup.com/api/v2/webhook/{WEBHOOK_ID}"
headers = {
    "Authorization": CLICKUP_TOKEN
}

res = requests.delete(url, headers=headers)
print(res.status_code)
print(res.text)
