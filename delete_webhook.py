import requests
import os
from dotenv import load_dotenv

load_dotenv()

CLICKUP_TOKEN = os.getenv("CLICKUP_TOKEN")
WEBHOOK_ID = "60cd15aa-778e-4d03-b220-b1eed220f0e9"

url = f"https://api.clickup.com/api/v2/webhook/{WEBHOOK_ID}"
headers = {
    "Authorization": CLICKUP_TOKEN
}

res = requests.delete(url, headers=headers)
print(res.status_code)
print(res.text)
