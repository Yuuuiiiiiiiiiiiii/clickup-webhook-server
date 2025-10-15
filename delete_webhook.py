import requests
import os
from dotenv import load_dotenv

load_dotenv()

CLICKUP_TOKEN = os.getenv("CLICKUP_TOKEN")
WEBHOOK_ID = "f4aa47c7-88cc-4dd7-a360-f7c216c6a364"

url = f"https://api.clickup.com/api/v2/webhook/{WEBHOOK_ID}"
headers = {
    "Authorization": CLICKUP_TOKEN
}

res = requests.delete(url, headers=headers)
print(res.status_code)
print(res.text)
