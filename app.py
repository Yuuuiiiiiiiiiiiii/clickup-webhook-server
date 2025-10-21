# app.py
from flask import Flask, request, jsonify
import requests
import os
import json
import time
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

CLICKUP_TOKEN = os.getenv("CLICKUP_TOKEN")
HEADERS = {"Authorization": CLICKUP_TOKEN}

def parse_date(timestamp):
    return datetime.fromtimestamp(int(timestamp) / 1000, tz=timezone.utc)

def format_diff(diff_seconds):
    days = int(diff_seconds // 86400)
    hours = int((diff_seconds % 86400) // 3600)
    minutes = int((diff_seconds % 3600) // 60)
    return f"{days}d {hours}h {minutes}m"

def update_interval_field(task_id, field_name, interval_text):
    """更新Interval字段"""
    try:
        # 获取任务详情
        res = requests.get(f"https://api.clickup.com/api/v2/task/{task_id}", headers=HEADERS)
        if res.status_code != 200:
            print(f"❌ Failed to fetch task for update: {res.status_code}")
            return False
            
        fields = res.json().get("custom_fields", [])
        
        # 查找指定的Interval字段
        interval_field = None
        for field in fields:
            if field.get("name") == field_name:
                interval_field = field
                break
                
        if not interval_field:
            print(f"❌ {field_name} field not found.")
            return False

        field_id = interval_field["id"]
        url = f"https://api.clickup.com/api/v2/task/{task_id}/field/{field_id}"
        data = {"value": interval_text}
        
        r = requests.post(url, headers=HEADERS, json=data)
        print(f"✅ Updated {field_name}: {interval_text}")
        
        return r.status_code in (200, 201)
        
    except Exception as e:
        print(f"❌ Error updating {field_name}: {str(e)}")
        return False

def calculate_all_intervals(task_id):
    """计算所有可能的间隔"""
    # 获取任务详情
    res = requests.get(f"https://api.clickup.com/api/v2/task/{task_id}", headers=HEADERS)
    if res.status_code != 200:
        print(f"❌ Failed to fetch task: {res.status_code}")
        return
    
    task = res.json()
    fields = task.get("custom_fields", [])
    
    # 创建字段字典
    cf = {f["name"]: f for f in fields}
    
    # 获取日期字段
    t1_date = cf.get("📅 T1 Date", {}).get("value")
    t2_date = cf.get("📅 T2 Date", {}).get("value") 
    t3_date = cf.get("📅 T3 Date", {}).get("value")
    t4_date = cf.get("📅 T4 Date", {}).get("value")
    
    print(f"📅 Dates - T1: {t1_date}, T2: {t2_date}, T3: {t3_date}, T4: {t4_date}")
    
    # 计算 Interval 1-2
    if t1_date and t2_date:
        d1 = parse_date(t1_date)
        d2 = parse_date(t2_date)
        diff_seconds = (d2 - d1).total_seconds()
        if diff_seconds >= 0:
            interval_12 = format_diff(diff_seconds)
            update_interval_field(task_id, "Interval 1-2", interval_12)
        else:
            update_interval_field(task_id, "Interval 1-2", "Invalid dates")
    else:
        # 如果缺少日期，清空Interval
        update_interval_field(task_id, "Interval 1-2", "")
    
    # 计算 Interval 2-3
    if t2_date and t3_date:
        d2 = parse_date(t2_date)
        d3 = parse_date(t3_date)
        diff_seconds = (d3 - d2).total_seconds()
        if diff_seconds >= 0:
            interval_23 = format_diff(diff_seconds)
            update_interval_field(task_id, "Interval 2-3", interval_23)
        else:
            update_interval_field(task_id, "Interval 2-3", "Invalid dates")
    else:
        update_interval_field(task_id, "Interval 2-3", "")
    
    # 计算 Interval 3-4
    if t3_date and t4_date:
        d3 = parse_date(t3_date)
        d4 = parse_date(t4_date)
        diff_seconds = (d4 - d3).total_seconds()
        if diff_seconds >= 0:
            interval_34 = format_diff(diff_seconds)
            update_interval_field(task_id, "Interval 3-4", interval_34)
        else:
            update_interval_field(task_id, "Interval 3-4", "Invalid dates")
    else:
        update_interval_field(task_id, "Interval 3-4", "")

@app.route("/clickup-webhook", methods=["POST"])
def clickup_webhook():
    data = request.json
    print("✅ Webhook received")

    # 获取task_id
    task_id = data.get("task_id") or (data.get("task") and data.get("task").get("id"))
    if not task_id:
        print("❌ No task_id found")
        return jsonify({"error": "no task_id"}), 400

    print(f"🎯 Processing task: {task_id}")
    
    # 直接计算所有间隔
    calculate_all_intervals(task_id)
    
    return jsonify({"success": True}), 200

@app.route("/")
def home():
    return "ClickUp Webhook Server running", 200

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)