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
    try:
        # 获取任务详情
        res = requests.get(f"https://api.clickup.com/api/v2/task/{task_id}", headers=HEADERS)
        if res.status_code != 200:
            print(f"❌ Failed to fetch task for update: {res.status_code}")
            return False
            
        fields = res.json().get("custom_fields", [])
        
        # 查找Interval字段
        interval_field = None
        for field in fields:
            if field.get("name") in ["Interval 1-2", "Interval"]:
                interval_field = field
                break
                
        if not interval_field:
            print("❌ Interval field not found. Available fields:")
            for field in fields:
                print(f"  - {field.get('name')} (ID: {field.get('id')})")
            return False

        field_id = interval_field["id"]
        url = f"https://api.clickup.com/api/v2/task/{task_id}/field/{field_id}"
        data = {"value": interval_text}
        
        r = requests.post(url, headers=HEADERS, json=data)
        print(f"📤 Update API response: {r.status_code} - {r.text}")
        
        return r.status_code in (200, 201)
        
    except Exception as e:
        print(f"❌ Error in update_interval: {str(e)}")
        return False

@app.route("/clickup-webhook", methods=["POST"])
def clickup_webhook():
    data = request.json
    print("✅ Webhook received at /clickup-webhook")
    print("📦 Full payload:", json.dumps(data, indent=2, ensure_ascii=False))

    # 更可靠的task_id获取方式
    task_id = data.get("task_id") or (data.get("task") and data.get("task").get("id"))
    if not task_id:
        print("❌ No task_id found in payload")
        return jsonify({"error": "no task_id"}), 400

    print(f"🎯 Processing task: {task_id}")

    # 获取任务详情
    res = requests.get(f"https://api.clickup.com/api/v2/task/{task_id}", headers=HEADERS)
    if res.status_code != 200:
        print(f"❌ Failed to fetch task: {res.status_code} - {res.text}")
        return jsonify({"error": "fetch task failed"}), 500
    
    task = res.json()
    fields = task.get("custom_fields", [])
    
    # 打印所有自定义字段用于调试
    print("🔍 All custom fields:")
    for field in fields:
        print(f"  - {field.get('name')}: {field.get('value')} (type: {field.get('type')})")

    # 查找需要的字段
    cf = {f["name"]: f for f in fields}
    
    # 使用你的实际字段名（注意可能没有emoji）
    t1_date = cf.get("T1 Date", {}).get("value") or cf.get("📅 T1 Date", {}).get("value")
    t2_date = cf.get("T2 Date", {}).get("value") or cf.get("📅 T2 Date", {}).get("value")
    t2_check = cf.get("Touch 2", {}).get("value") or cf.get("✅ Touch 2", {}).get("value")

    print(f"📊 Field values - T1: {t1_date}, T2: {t2_date}, T2 Check: {t2_check}")

    # 检查条件
    if not all([t1_date, t2_date]):
        print("❌ Missing dates")
        return jsonify({"error": "missing dates"}), 200
        
    if not t2_check:
        print("❌ T2 not checked")
        return jsonify({"error": "t2 not checked"}), 200

    # 计算时间差
    try:
        d1 = parse_date(t1_date)
        d2 = parse_date(t2_date)
        diff_seconds = (d2 - d1).total_seconds()
        
        if diff_seconds < 0:
            print("❌ Negative time difference")
            return jsonify({"error": "negative time difference"}), 200
            
        interval = format_diff(diff_seconds)
        print(f"⏱️ Calculated interval: {interval}")
        
        # 更新字段
        success = update_interval(task_id, interval)
        if success:
            print("🎉 Successfully updated interval!")
            return jsonify({"success": True, "interval": interval}), 200
        else:
            print("❌ Failed to update interval field")
            return jsonify({"error": "update failed"}), 500
            
    except Exception as e:
        print(f"❌ Error in calculation: {str(e)}")
        return jsonify({"error": "calculation error"}), 500
        
@app.route("/")
def home():
    return "ClickUp Webhook Server running", 200

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()  # ✅ 在部署环境中也加载 .env
    port = int(os.environ.get("PORT", 10000))  # ✅ Render 自动注入 PORT
    app.run(host="0.0.0.0", port=port)