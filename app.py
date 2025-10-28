from flask import Flask, request, jsonify
import requests
import os
import json
import time
import threading
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

CLICKUP_TOKEN = os.getenv("CLICKUP_TOKEN")
HEADERS = {"Authorization": CLICKUP_TOKEN}

# 🔥 彻底杀死重复webhook的武器
webhook_lock = threading.Lock()
recent_webhooks = {}

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
        res = requests.get(f"https://api.clickup.com/api/v2/task/{task_id}", headers=HEADERS)
        if res.status_code != 200:
            return False
            
        fields = res.json().get("custom_fields", [])
        
        for field in fields:
            if field.get("name") == field_name:
                field_id = field["id"]
                url = f"https://api.clickup.com/api/v2/task/{task_id}/field/{field_id}"
                data = {"value": interval_text}
                
                r = requests.post(url, headers=HEADERS, json=data)
                return r.status_code in (200, 201)
                
        return False
        
    except Exception:
        return False

def calculate_all_intervals(task_id):
    """计算所有日期间隔"""
    res = requests.get(f"https://api.clickup.com/api/v2/task/{task_id}", headers=HEADERS)
    if res.status_code != 200:
        return
    
    task = res.json()
    fields = task.get("custom_fields", [])
    
    # 直接提取日期字段值
    t1_date = None
    t2_date = None  
    t3_date = None
    t4_date = None
    
    for field in fields:
        name = field.get("name", "")
        value = field.get("value")
        
        if "📅 T1 Date" in name:
            t1_date = value
        elif "📅 T2 Date" in name:
            t2_date = value
        elif "📅 T3 Date" in name:
            t3_date = value
        elif "📅 T4 Date" in name:
            t4_date = value
    
    print(f"📅 日期状态: T1={t1_date}, T2={t2_date}, T3={t3_date}, T4={t4_date}")
    
    # 计算 Interval 1-2
    if t1_date and t2_date:
        d1 = parse_date(t1_date)
        d2 = parse_date(t2_date)
        diff_seconds = (d2 - d1).total_seconds()
        if diff_seconds >= 0:
            interval_12 = format_diff(diff_seconds)
            print(f"✅ 更新 Interval 1-2: {interval_12}")
            update_interval_field(task_id, "Interval 1-2", interval_12)
    else:
        print("🔄 清空 Interval 1-2")
        update_interval_field(task_id, "Interval 1-2", "")
    
    # 计算 Interval 2-3
    if t2_date and t3_date:
        d2 = parse_date(t2_date)
        d3 = parse_date(t3_date)
        diff_seconds = (d3 - d2).total_seconds()
        if diff_seconds >= 0:
            interval_23 = format_diff(diff_seconds)
            print(f"✅ 更新 Interval 2-3: {interval_23}")
            update_interval_field(task_id, "Interval 2-3", interval_23)
    else:
        print("🔄 清空 Interval 2-3")
        update_interval_field(task_id, "Interval 2-3", "")
    
    # 计算 Interval 3-4
    if t3_date and t4_date:
        d3 = parse_date(t3_date)
        d4 = parse_date(t4_date)
        diff_seconds = (d4 - d3).total_seconds()
        if diff_seconds >= 0:
            interval_34 = format_diff(diff_seconds)
            print(f"✅ 更新 Interval 3-4: {interval_34}")
            update_interval_field(task_id, "Interval 3-4", interval_34)
    else:
        print("🔄 清空 Interval 3-4")
        update_interval_field(task_id, "Interval 3-4", "")

def handle_order_client_linking(task_id):
    """处理Order Record的客户链接"""
    print(f"🔗 Processing client linking for Order Record: {task_id}")
    
    res = requests.get(f"https://api.clickup.com/api/v2/task/{task_id}", headers=HEADERS)
    if res.status_code != 200:
        print(f"❌ Failed to fetch order task: {res.status_code}")
        return
        
    task = res.json()
    fields = task.get("custom_fields", [])
    
    # 获取👤 Client Name字段值和👤 Client字段ID
    client_name = None
    client_field_id = None
    
    for field in fields:
        field_name = field.get("name", "")
        field_value = field.get("value")
        field_id = field.get("id")
        
        if "👤 Client Name" == field_name:
            client_name = field_value
            print(f"📝 Found Client Name: {client_name}")
            
        elif "👤 Client" == field_name:
            client_field_id = field_id
            print(f"🆔 Found Client relationship field ID: {client_field_id}")
    
    if not client_name or not client_field_id:
        return
    
    print(f"🎯 Looking for client: '{client_name}' in Customer List")
    
    # 在Customer List中查找匹配的客户
    CUSTOMER_LIST_ID = "901811834458"
    
    search_url = f"https://api.clickup.com/api/v2/list/{CUSTOMER_LIST_ID}/task"
    params = {"archived": "false"}
    search_res = requests.get(search_url, headers=HEADERS, params=params)
    
    if search_res.status_code == 200:
        customer_tasks = search_res.json().get("tasks", [])
        print(f"🔍 Found {len(customer_tasks)} tasks in Customer List")
        
        # 精确匹配客户名称
        matched_task = None
        for customer_task in customer_tasks:
            customer_name = customer_task.get("name", "").strip()
            if customer_name.lower() == client_name.strip().lower():
                matched_task = customer_task
                print(f"✅ Exact match found: '{customer_name}' -> {customer_task.get('id')}")
                break
        
        if matched_task:
            client_task_id = matched_task.get("id")
            
            # 使用正确的关系字段API格式
            update_url = f"https://api.api.clickup.com/api/v2/task/{task_id}/field/{client_field_id}"
            
            payload = {
                "value": {
                    "add": [client_task_id],
                    "rem": []
                }
            }
            
            headers_with_content = HEADERS.copy()
            headers_with_content["Content-Type"] = "application/json"
            
            update_res = requests.post(update_url, headers=headers_with_content, json=payload)
            print(f"📡 API response status: {update_res.status_code}")
            
            if update_res.status_code in (200, 201):
                print(f"✅ Relationship field updated successfully!")
            else:
                print(f"❌ Failed to update relationship field")
        else:
            print(f"❌ No matching client found for: '{client_name}'")
    else:
        print(f"❌ Failed to search Customer List: {search_res.status_code}")

def cleanup_old_webhooks():
    """清理旧的webhook记录"""
    current_time = time.time()
    with webhook_lock:
        to_delete = [task_id for task_id, timestamp in recent_webhooks.items() 
                    if current_time - timestamp > 30]
        for task_id in to_delete:
            del recent_webhooks[task_id]
        if to_delete:
            print(f"🧹 清理了 {len(to_delete)} 个旧webhook记录")

@app.route("/clickup-webhook", methods=["POST"])
def clickup_webhook():
    data = request.json
    print("✅ Webhook received")
    
    task_id = data.get("task_id") or (data.get("task") and data.get("task").get("id"))
    if not task_id:
        print("❌ No task_id found")
        return jsonify({"error": "no_task_id"}), 400

    # 🔥 核心武器：彻底杀死重复webhook
    current_time = time.time()
    with webhook_lock:
        if task_id in recent_webhooks:
            last_time = recent_webhooks[task_id]
            # 5秒内同一个任务的webhook直接枪毙
            if current_time - last_time < 5:
                print(f"🔫 直接杀死重复webhook: {task_id}")
                return jsonify({"killed": "duplicate"}), 200
        
        # 记录这个webhook
        recent_webhooks[task_id] = current_time
    
    # 偶尔清理一下旧记录
    if len(recent_webhooks) > 100:
        cleanup_old_webhooks()

    print(f"🎯 Processing task: {task_id}")
    
    try:
        # 获取任务详情来判断是哪个列表
        res = requests.get(f"https://api.clickup.com/api/v2/task/{task_id}", headers=HEADERS)
        if res.status_code == 200:
            task = res.json()
            list_id = task.get("list", {}).get("id")
            
            # 根据列表ID决定处理逻辑
            if list_id == "901811834458":  # Customer List
                print("🔄 Processing as Customer List task (Interval calculation)")
                calculate_all_intervals(task_id)
                
            elif list_id == "901812062655":  # Order Record List  
                print("🆕 Processing as Order Record task (Client linking)")
                handle_order_client_linking(task_id)
                
    except Exception as e:
        print(f"⚠️ Exception while processing task: {str(e)}")
    
    return jsonify({"success": True}), 200

@app.route("/")
def home():
    return "ClickUp Webhook Server running", 200

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)