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

# 改进的去重系统
task_processing_state = {}  # task_id -> {"last_processed": timestamp, "last_date_state": (t1,t2,t3,t4)}
PROCESS_COOLDOWN = 5  # 增加到5秒

# API 调用跟踪
api_calls_this_minute = 0
minute_start = time.time()

def check_api_limit():
    """简单的API限制检查"""
    global api_calls_this_minute, minute_start
    
    current_time = time.time()
    # 每分钟重置
    if current_time - minute_start >= 60:
        api_calls_this_minute = 0
        minute_start = current_time
    
    # 如果接近限制，等待
    if api_calls_this_minute >= 90:
        wait_time = 60 - (current_time - minute_start)
        if wait_time > 0:
            print(f"⏳ 接近API限制，等待 {wait_time:.1f}秒")
            time.sleep(wait_time + 1)  # 多加1秒确保安全
            api_calls_this_minute = 0
            minute_start = time.time()

def safe_api_call(url, method='GET', json_data=None):
    """安全的API调用"""
    global api_calls_this_minute
    check_api_limit()
    
    headers = HEADERS.copy()
    if method == 'POST':
        headers["Content-Type"] = "application/json"
        response = requests.post(url, headers=headers, json=json_data)
    else:
        response = requests.get(url, headers=headers)
    
    api_calls_this_minute += 1
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

def get_current_date_state(task_id):
    """获取当前日期字段状态"""
    try:
        res = safe_api_call(f"https://api.clickup.com/api/v2/task/{task_id}")
        if res.status_code != 200:
            return None
            
        task = res.json()
        fields = task.get("custom_fields", [])
        
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
        
        return (dates.get('t1'), dates.get('t2'), dates.get('t3'), dates.get('t4'))
        
    except Exception as e:
        print(f"❌ 获取日期状态失败: {str(e)}")
        return None

def dates_changed(task_id, current_dates):
    """检查日期字段是否真正发生变化"""
    if task_id not in task_processing_state:
        return True  # 第一次处理
    
    last_dates = task_processing_state[task_id].get("last_date_state")
    if last_dates != current_dates:
        return True
    
    return False

def update_interval_field(task_id, field_name, interval_text):
    """更新Interval字段"""
    try:
        # 先获取任务信息来找到字段ID
        res = safe_api_call(f"https://api.clickup.com/api/v2/task/{task_id}")
        if res.status_code != 200:
            return False
            
        fields = res.json().get("custom_fields", [])
        
        # 查找目标字段
        for field in fields:
            if field.get("name") == field_name:
                field_id = field["id"]
                url = f"https://api.clickup.com/api/v2/task/{task_id}/field/{field_id}"
                data = {"value": interval_text}
                
                r = safe_api_call(url, method='POST', json_data=data)
                success = r.status_code in (200, 201)
                if success:
                    print(f"✅ 更新 {field_name}: {interval_text}")
                return success
                
        return False
        
    except Exception as e:
        print(f"❌ 更新字段失败: {str(e)}")
        return False

def calculate_all_intervals(task_id):
    """计算所有日期间隔 - 优化版本"""
    current_dates = get_current_date_state(task_id)
    if not current_dates:
        return
    
    t1_date, t2_date, t3_date, t4_date = current_dates
    
    print(f"📅 日期状态: T1={t1_date}, T2={t2_date}, T3={t3_date}, T4={t4_date}")
    
    # 只在日期真正变化时才计算
    if not dates_changed(task_id, current_dates):
        print("⏭️ 日期未变化，跳过计算")
        return
    
    # 计算 Interval 1-2 (需要T1和T2都有值)
    if t1_date and t2_date:
        d1 = parse_date(t1_date)
        d2 = parse_date(t2_date)
        if d1 and d2:
            diff_seconds = (d2 - d1).total_seconds()
            interval_12 = format_diff(diff_seconds)
            update_interval_field(task_id, "Interval 1-2", interval_12)
    else:
        update_interval_field(task_id, "Interval 1-2", "")
    
    # 计算 Interval 2-3 (需要T2和T3都有值)
    if t2_date and t3_date:
        d2 = parse_date(t2_date)
        d3 = parse_date(t3_date)
        if d2 and d3:
            diff_seconds = (d3 - d2).total_seconds()
            interval_23 = format_diff(diff_seconds)
            update_interval_field(task_id, "Interval 2-3", interval_23)
    else:
        update_interval_field(task_id, "Interval 2-3", "")
    
    # 计算 Interval 3-4 (需要T3和T4都有值)
    if t3_date and t4_date:
        d3 = parse_date(t3_date)
        d4 = parse_date(t4_date)
        if d3 and d4:
            diff_seconds = (d4 - d3).total_seconds()
            interval_34 = format_diff(diff_seconds)
            update_interval_field(task_id, "Interval 3-4", interval_34)
    else:
        update_interval_field(task_id, "Interval 3-4", "")
    
    # 更新处理状态
    if task_id not in task_processing_state:
        task_processing_state[task_id] = {}
    
    task_processing_state[task_id]["last_date_state"] = current_dates
    task_processing_state[task_id]["last_processed"] = time.time()

def handle_order_client_linking(task_id):
    """处理Order Record的客户链接 - 只在创建时调用"""
    print(f"🔗 Processing client linking for Order Record: {task_id}")
    
    res = safe_api_call(f"https://api.clickup.com/api/v2/task/{task_id}")
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
    
    if not client_name:
        print("⏭️ No 👤 Client Name found in Order Record")
        return
        
    if not client_field_id:
        print("❌ 👤 Client relationship field not found in Order Record")
        return
    
    print(f"🎯 Looking for client: '{client_name}' in Customer List")
    
    # 在Customer List中查找匹配的客户
    CUSTOMER_LIST_ID = "901811834458"
    
    search_url = f"https://api.clickup.com/api/v2/list/{CUSTOMER_LIST_ID}/task"
    params = {"archived": "false"}
    search_res = safe_api_call(search_url, params=params)
    
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
            update_url = f"https://api.clickup.com/api/v2/task/{task_id}/field/{client_field_id}"
            
            payload = {
                "value": {
                    "add": [client_task_id],
                    "rem": []
                }
            }
            
            update_res = safe_api_call(update_url, method='POST', json_data=payload)
            print(f"📡 API response status: {update_res.status_code}")
            
            if update_res.status_code in (200, 201):
                print(f"✅ Relationship field updated successfully!")
            else:
                print(f"❌ Failed to update relationship field: {update_res.text}")
        else:
            print(f"❌ No matching client found for: '{client_name}'")
    else:
        print(f"❌ Failed to search Customer List: {search_res.status_code}")

@app.route("/clickup-webhook", methods=["POST"])
def clickup_webhook():
    data = request.json
    print("✅ Webhook received")
    
    # 获取任务ID和事件类型
    task_id = data.get("task_id") or (data.get("task") and data.get("task").get("id"))
    event_type = data.get('event', '')
    
    if not task_id:
        print("❌ No task_id found")
        return jsonify({"error": "no task_id"}), 400

    print(f"🎯 Processing task: {task_id}, Event: {event_type}")

    # 改进的去重检查
    current_time = time.time()
    if task_id in task_processing_state:
        state = task_processing_state[task_id]
        last_time = state.get("last_processed", 0)
        
        # 如果在冷却期内，直接跳过
        if current_time - last_time < PROCESS_COOLDOWN:
            print(f"⏭️ Skipping duplicate request for task {task_id} (in cooldown)")
            return jsonify({"ignored": "duplicate"}), 200
    
    try:
        # 获取任务详情来判断是哪个列表
        res = safe_api_call(f"https://api.clickup.com/api/v2/task/{task_id}")
        if res.status_code == 200:
            task = res.json()
            list_id = task.get("list", {}).get("id")
            
            print(f"📁 List ID: {list_id}")
            
            # Customer List: 计算间隔
            if list_id == "901811834458":  # Customer List
                print("🔄 Processing as Customer List task (Interval calculation)")
                calculate_all_intervals(task_id)
                
            # Order Record: 只在创建时链接客户
            elif list_id == "901812062655":  # Order Record List
                if event_type == 'taskCreated':
                    print("🆕 Processing as Order Record task (Client linking - taskCreated)")
                    handle_order_client_linking(task_id)
                else:
                    print(f"⏭️ Skipping Order Record task (event: {event_type})")
                    
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
    