# app.py
from flask import Flask, request, jsonify
import requests
import os
import json
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

CLICKUP_TOKEN = os.getenv("CLICKUP_TOKEN")  # set this in .env locally and in Render env vars
HEADERS = {"Authorization": CLICKUP_TOKEN}

def parse_date(timestamp):
    return datetime.fromtimestamp(int(timestamp) / 1000, tz=timezone.utc)

def format_diff(diff_seconds):
    days = diff_seconds // 86400
    hours = (diff_seconds % 86400) // 3600
    minutes = (diff_seconds % 3600) // 60
    return f"{days}d {hours}h {minutes}m"

def update_interval(task_id, interval_text):
    # 从 /task/{task_id} 获取 custom fields，找到 Interval 1-2 并更新
    res = requests.get(f"https://api.clickup.com/api/v2/task/{task_id}", headers=HEADERS)
    if res.status_code != 200:
        print("Failed to fetch task:", res.status_code, res.text)
        return False
    fields = res.json().get("custom_fields", [])
    interval_field = next((f for f in fields if f["name"] == "Interval 1-2"), None)
    if not interval_field:
        print("找不到 Interval 1-2 custom field")
        return False

    field_id = interval_field["id"]
    url = f"https://api.clickup.com/api/v2/task/{task_id}/field/{field_id}"
    data = {"value": interval_text}
    r = requests.post(url, headers=HEADERS, json=data)
    print(f"Update Interval result: {r.status_code} {r.text}")
    return r.status_code in (200, 201)

@app.route("/clickup-webhook", methods=["POST"])
def clickup_webhook():
    data = request.json
    print("Webhook payload:", json.dumps(data, ensure_ascii=False))
    # task id 可能在顶层 task_id 或者 data["task"]["id"]
    task_id = data.get("task_id") or data.get("task", {}).get("id")
    if not task_id:
        print("没有 task_id，忽略")
        return jsonify({"error": "no task_id"}), 400

    # 取任务详情（以防 payload 没带 custom_fields）
    res = requests.get(f"https://api.clickup.com/api/v2/task/{task_id}", headers=HEADERS)
    if res.status_code != 200:
        print("不能取得任务详情:", res.status_code, res.text)
        return jsonify({"error": "fetch task failed"}), 500
    task = res.json()
    fields = task.get("custom_fields", [])
    cf = {f["name"]: f for f in fields}

    # 这里按你实际 custom field 名称改（包含 emoji）
    t1 = cf.get("📅 T1 Date", {}).get("value")
    t2 = cf.get("📅 T2 Date", {}).get("value")
    t2check = cf.get("✅ Touch 2", {}).get("value", False)

    if t1 and t2 and t2check:
        d1 = parse_date(t1)
        d2 = parse_date(t2)
        diff = int((d2 - d1).total_seconds())
        interval = format_diff(diff)
        ok = update_interval(task_id, interval)
        if ok:
            return jsonify({"ok": True, "interval": interval}), 200
        else:
            return jsonify({"ok": False}), 500

    print("数据不完整或 T2 未勾选")
    return jsonify({"ignored": True}), 200

@app.route("/")
def home():
    return "ClickUp Webhook Server running", 200

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()  # ✅ 在部署环境中也加载 .env
    port = int(os.environ.get("PORT", 10000))  # ✅ Render 自动注入 PORT
    app.run(host="0.0.0.0", port=port)