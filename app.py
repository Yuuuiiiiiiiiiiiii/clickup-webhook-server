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

# 请求去重缓存 - 简化版本
processed_tasks = {}
PROCESS_COOLDOWN = 2  # 2秒去重

# API 调用计数器
api_call_count = 0
last_reset_time = time.time()

def check_rate_limit():
    """简单的速率限制检查"""
    global api_call_count, last_reset_time
    
    current_time = time.time()
    # 每分钟重置计数器
    if current_time - last_reset_time >= 60:
        api_call_count = 0
        last_reset_time = current_time
    
    # 如果接近限制，等待一下
    if api_call_count >= 95:
        wait_time = 60 - (current_time - last_reset_time)
        if wait_time > 0:
            print(f"⚠️ API 限制接近，等待 {wait_time:.1f} 秒")
            time.sleep(wait_time)
            api_call_count = 0
            last_reset_time = time.time()

def make_api_call(url, method='GET', json_data=None):
    """包装 API 调用，包含速率限制"""
    global api_call_count
    check_rate_limit()
    
    headers = HEADERS.copy()
    if method == 'POST':
        headers["Content-Type"] = "application/json"
        response = requests.post(url, headers=headers, json=json_data)
    else:
        response = requests.get(url, headers=headers)
    
    api_call_count += 1
    return response

def parse_date(timestamp):
    """解析时间戳"""
    try:
        return datetime.fromtimestamp(int(timestamp) / 1000, tz=timezone.utc)
    except (ValueError, TypeError):
        return None

def format_diff(diff_seconds):
    """格式化时间差"""
    if diff_seconds < 0:
        return ""
    
    days = int(diff_seconds // 86400)
    hours = int((diff_seconds % 86400) // 3600)
    minutes = int((diff_seconds % 3600) // 60)
    return f"{days}d {hours}h {minutes}m"

def update_interval_field(task_id, field_name, interval_text):
    """更新 Interval 字段"""
    try:
        # 先获取任务信息来找到字段ID
        res = make_api_call(f"https://api.clickup.com/api/v2/task/{task_id}")
        if res.status_code != 200:
            return False
            
        fields = res.json().get("custom_fields", [])
        
        # 查找目标字段
        for field in fields:
            if field.get("name") == field_name:
                field_id = field["id"]
                url = f"https://api.clickup.com/api/v2/task/{task_id}/field/{field_id}"
                data = {"value": interval_text}
                
                r = make_api_call(url, method='POST', json_data=data)
                return r.status_code in (200, 201)
                
        return False
        
    except Exception as e:
        print(f"❌ 更新字段失败: {str(e)}")
        return False

def calculate_all_intervals(task_id):
    """计算所有日期间隔 - 优化版本"""
    try:
        res = make_api_call(f"https://api.clickup.com/api/v2/task/{task_id}")
        if res.status_code != 200:
            return
        
        task = res.json()
        fields = task.get("custom_fields", [])
        
        # 提取日期字段值
        dates = {}
        for field in fields:
            name = field.get("name", "")
            value = field.get("value")
            
            if "📅 T1 Date" in name:
                dates['t1'] = value
            elif "📅 T2 Date" in name:
                dates['t2'] = value
            elif "📅 T3 Date" in name:
                dates['t3'] = value
            elif "📅 T4 Date" in name:
                dates['t4'] = value
        
        # 计算 Interval 1-2 (需要 T1 和 T2 都有值)
        if dates.get('t1') and dates.get('t2'):
            d1 = parse_date(dates['t1'])
            d2 = parse_date(dates['t2'])
            if d1 and d2:
                diff_seconds = (d2 - d1).total_seconds()
                interval_12 = format_diff(diff_seconds)
                update_interval_field(task_id, "Interval 1-2", interval_12)
        else:
            update_interval_field(task_id, "Interval 1-2", "")
        
        # 计算 Interval 2-3 (需要 T2 和 T3 都有值)
        if dates.get('t2') and dates.get('t3'):
            d2 = parse_date(dates['t2'])
            d3 = parse_date(dates['t3'])
            if d2 and d3:
                diff_seconds = (d3 - d2).total_seconds()
                interval_23 = format_diff(diff_seconds)
                update_interval_field(task_id, "Interval 2-3", interval_23)
        else:
            update_interval_field(task_id, "Interval 2-3", "")
        
        # 计算 Interval 3-4 (需要 T3 和 T4 都有值)
        if dates.get('t3') and dates.get('t4'):
            d3 = parse_date(dates['t3'])
            d4 = parse_date(dates['t4'])
            if d3 and d4:
                diff_seconds = (d4 - d3).total_seconds()
                interval_34 = format_diff(diff_seconds)
                update_interval_field(task_id, "Interval 3-4", interval_34)
        else:
            update_interval_field(task_id, "Interval 3-4", "")
            
        print(f"✅ 间隔计算完成: {task_id}")
        
    except Exception as e:
        print(f"❌ 计算间隔失败: {str(e)}")

def handle_order_client_linking(task_id):
    """处理 Order Record 的客户链接 - 只在创建时调用"""
    print(f"🔗 Processing client linking for Order Record: {task_id}")
    
    res = make_api_call(f"https://api.clickup.com/api/v2/task/{task_id}")
    if res.status_code != 200:
        print(f"❌ Failed to fetch order task: {res.status_code}")
        return
        
    task = res.json()
    fields = task.get("custom_fields", [])
    
    # 获取👤 Client Name字段值和👤 Client字段ID
    client_name = None
    client_field_id = None
    
    print("🔍 Searching for fields in Order Record:")
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
    
    if not client_name:
        print("⏭️ No 👤 Client Name found in Order Record")
        return
        
    if not client_field_id:
        print("❌ 👤 Client relationship field not found in Order Record")
        return
    
    print(f"🎯 Looking for client: '{client_name}' in Customer List")
    
    # 在 Customer List 中查找匹配的客户
    CUSTOMER_LIST_ID = "901811834458"
    
    search_url = f"https://api.clickup.com/api/v2/list/{CUSTOMER_LIST_ID}/task"
    params = {"archived": "false"}
    search_res = make_api_call(search_url, params=params)
    
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
            
            # 更新关系字段
            print("🔄 Using correct Relationship Field API format")
            update_url = f"https://api.clickup.com/api/v2/task/{task_id}/field/{client_field_id}"
            
            payload = {
                "value": {
                    "add": [client_task_id],
                    "rem": []
                }
            }
            
            update_res = make_api_call(update_url, method='POST', json_data=payload)
            print(f"📡 API response status: {update_res.status_code}")
            
            if update_res.status_code in (200, 201):
                print(f"✅ Relationship field updated successfully!")
            else:
                print(f"❌ Failed to update relationship field: {update_res.text}")
        else:
            print(f"❌ No matching client found for: '{client_name}'")
    else:
        print(f"❌ Failed to search Customer List: {search_res.status_code}")

def should_process_date_update(webhook_data, task_data):
    """检查是否应该处理日期更新"""
    # 检查事件类型
    event = webhook_data.get('event')
    if not event:
        return False
    
    # 只处理任务更新事件
    if event != 'taskUpdated':
        return False
    
    # 检查是否有字段更新
    history_items = webhook_data.get('history_items', [])
    if not history_items:
        return False
    
    # 检查是否有日期字段被更新
    date_fields = ["📅 T1 Date", "📅 T2 Date", "📅 T3 Date", "📅 T4 Date"]
    for item in history_items:
        field = item.get('field')
        if field in date_fields:
            print(f"✅ 检测到日期字段更新: {field}")
            return True
    
    return False

@app.route("/clickup-webhook", methods=["POST"])
def clickup_webhook():
    data = request.json
    print("✅ Webhook received")
    
    # 获取任务ID
    task_id = data.get("task_id") or (data.get("task") and data.get("task").get("id"))
    if not task_id:
        print("❌ No task_id found")
        return jsonify({"error": "no task_id"}), 400

    # 简单的去重检查
    current_time = time.time()
    if task_id in processed_tasks:
        last_time = processed_tasks[task_id]
        if current_time - last_time < PROCESS_COOLDOWN:
            print(f"⏭️ Skipping duplicate request for task {task_id}")
            return jsonify({"ignored": "duplicate"}), 200
    
    processed_tasks[task_id] = current_time

    print(f"🎯 Processing task: {task_id}")
    
    try:
        # 获取任务详情来判断是哪个列表
        res = make_api_call(f"https://api.clickup.com/api/v2/task/{task_id}")
        if res.status_code != 200:
            print(f"❌ Failed to fetch task: {res.status_code}")
            return jsonify({"error": "fetch_failed"}), 500
            
        task = res.json()
        list_id = task.get("list", {}).get("id")
        event_type = data.get('event', '')
        
        print(f"📁 List ID: {list_id}, Event: {event_type}")
        
        # Customer List: 只在日期字段更新时计算间隔
        if list_id == "901811834458":  # Customer List
            if should_process_date_update(data, task):
                print("🔄 Processing as Customer List task (Date field updated)")
                calculate_all_intervals(task_id)
            else:
                print("⏭️ Skipping Customer List task (no date field update)")
                
        # Order Record: 只在任务创建时链接客户
        elif list_id == "901812062655":  # Order Record List
            if event_type == 'taskCreated':
                print("🆕 Processing as Order Record task (Client linking - taskCreated)")
                handle_order_client_linking(task_id)
            else:
                print("⏭️ Skipping Order Record task (not taskCreated event)")
                
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
    