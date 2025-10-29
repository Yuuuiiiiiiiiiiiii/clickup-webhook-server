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

# API 调用跟踪
api_call_timestamps = []
api_lock = threading.Lock()

# Webhook 去重
webhook_timestamps = {}
webhook_lock = threading.Lock()

def safe_api_call(url, method='GET', json_data=None, max_retries=2):
    """安全的 API 调用，包含速率限制和重试"""
    global api_call_timestamps
    
    # 检查 API 限制
    current_time = time.time()
    with api_lock:
        # 移除1分钟前的记录
        api_call_timestamps = [ts for ts in api_call_timestamps if current_time - ts < 60]
        
        # 如果接近限制，等待
        if len(api_call_timestamps) >= 90:  # 留10个缓冲
            oldest_call = min(api_call_timestamps)
            wait_time = 60 - (current_time - oldest_call)
            if wait_time > 0:
                print(f"⏳ 接近API限制，等待 {wait_time:.1f}秒")
                time.sleep(wait_time + 1)
                # 重置计数器
                api_call_timestamps.clear()
    
    # 执行请求
    headers = HEADERS.copy()
    if method == 'POST':
        headers["Content-Type"] = "application/json"
    
    for attempt in range(max_retries + 1):
        try:
            if method == 'POST':
                response = requests.post(url, headers=headers, json=json_data, timeout=10)
            else:
                response = requests.get(url, headers=headers, timeout=10)
            
            # 记录成功的 API 调用
            with api_lock:
                api_call_timestamps.append(time.time())
            
            if response.status_code == 429:
                print(f"⚠️ API 限制触发，等待重试...")
                time.sleep(5)
                continue
                
            return response
            
        except requests.exceptions.Timeout:
            print(f"⏰ 请求超时，重试 {attempt + 1}/{max_retries + 1}")
            if attempt < max_retries:
                time.sleep(2)
                continue
            else:
                raise
        except Exception as e:
            print(f"❌ 请求异常: {str(e)}")
            if attempt < max_retries:
                time.sleep(2)
                continue
            else:
                raise
    
    return None

def parse_date(timestamp):
    try:
        return datetime.fromtimestamp(int(timestamp) / 1000, tz=timezone.utc)
    except (ValueError, TypeError):
        return None

def format_diff(diff_seconds):
    if diff_seconds < 0:
        return ""
    days = int(diff_seconds // 86400)
    hours = int((diff_seconds % 86400) // 3600)
    minutes = int((diff_seconds % 3600) // 60)
    return f"{days}d {hours}h {minutes}m"

def update_interval_field(task_id, field_name, interval_text):
    """更新Interval字段 - 安全版本"""
    try:
        res = safe_api_call(f"https://api.clickup.com/api/v2/task/{task_id}")
        if res.status_code != 200:
            print(f"❌ 获取任务失败: {res.status_code}")
            return False
            
        fields = res.json().get("custom_fields", [])
        
        for field in fields:
            if field.get("name") == field_name:
                field_id = field["id"]
                url = f"https://api.clickup.com/api/v2/task/{task_id}/field/{field_id}"
                data = {"value": interval_text}
                
                r = safe_api_call(url, method='POST', json_data=data)
                success = r.status_code in (200, 201)
                if success:
                    print(f"✅ 更新 {field_name}: {interval_text}")
                else:
                    print(f"❌ 更新失败 {field_name}: {r.status_code}")
                return success
                
        print(f"❌ 未找到字段: {field_name}")
        return False
        
    except Exception as e:
        print(f"❌ 更新字段异常: {str(e)}")
        return False

def calculate_all_intervals(task_id):
    """计算所有日期间隔 - 安全版本"""
    try:
        res = safe_api_call(f"https://api.clickup.com/api/v2/task/{task_id}")
        if res.status_code != 200:
            print(f"❌ 获取任务失败: {res.status_code}")
            return
        
        task = res.json()
        fields = task.get("custom_fields", [])
        
        # 提取日期字段值
        dates = {}
        for field in fields:
            name = field.get("name", "")
            value = field.get("value")
            
            if "📅 T1 Date" in name: dates['t1'] = value
            elif "📅 T2 Date" in name: dates['t2'] = value
            elif "📅 T3 Date" in name: dates['t3'] = value
            elif "📅 T4 Date" in name: dates['t4'] = value
        
        print(f"📅 日期状态: T1={dates.get('t1')}, T2={dates.get('t2')}, T3={dates.get('t3')}, T4={dates.get('t4')}")
        
        # 计算间隔
        if dates.get('t1') and dates.get('t2'):
            d1 = parse_date(dates['t1'])
            d2 = parse_date(dates['t2'])
            if d1 and d2:
                diff_seconds = (d2 - d1).total_seconds()
                interval_12 = format_diff(diff_seconds)
                update_interval_field(task_id, "Interval 1-2", interval_12)
        else:
            update_interval_field(task_id, "Interval 1-2", "")
        
        if dates.get('t2') and dates.get('t3'):
            d2 = parse_date(dates['t2'])
            d3 = parse_date(dates['t3'])
            if d2 and d3:
                diff_seconds = (d3 - d2).total_seconds()
                interval_23 = format_diff(diff_seconds)
                update_interval_field(task_id, "Interval 2-3", interval_23)
        else:
            update_interval_field(task_id, "Interval 2-3", "")
        
        if dates.get('t3') and dates.get('t4'):
            d3 = parse_date(dates['t3'])
            d4 = parse_date(dates['t4'])
            if d3 and d4:
                diff_seconds = (d4 - d3).total_seconds()
                interval_34 = format_diff(diff_seconds)
                update_interval_field(task_id, "Interval 3-4", interval_34)
        else:
            update_interval_field(task_id, "Interval 3-4", "")
            
    except Exception as e:
        print(f"❌ 计算间隔异常: {str(e)}")

def verify_relationship_update(task_id, client_field_id, expected_client_id):
    """验证关系字段更新是否成功"""
    print(f"🔍 Verifying relationship field update...")
    time.sleep(2)
    
    verify_res = safe_api_call(f"https://api.clickup.com/api/v2/task/{task_id}")
    if verify_res.status_code == 200:
        verify_task = verify_res.json()
        verify_fields = verify_task.get("custom_fields", [])
        
        for field in verify_fields:
            if field.get("id") == client_field_id:
                linked_value = field.get("value")
                print(f"   🔍 Client field current value: {linked_value}")
                
                if linked_value and len(linked_value) > 0:
                    if isinstance(linked_value[0], dict):
                        actual_id = linked_value[0].get('id')
                    else:
                        actual_id = linked_value[0]
                    
                    if actual_id == expected_client_id:
                        print(f"   🎉 SUCCESS! Client relationship established: {actual_id}")
                        return True
                    else:
                        print(f"   ⚠️ Client linked but with different ID: {actual_id} vs {expected_client_id}")
                        return True
                else:
                    print(f"   ❌ Client field is still empty!")
                    return False
        print(f"   ❌ Could not find Client field for verification")
        return False
    else:
        print(f"   ❌ Verification request failed: {verify_res.status_code}")
        return False

def handle_order_client_linking(task_id):
    """处理Order Record的客户链接 - 完整版本"""
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
            
            # 使用正确的关系字段API格式 - 完整版本
            print("🔄 Using correct Relationship Field API format")
            update_url = f"https://api.clickup.com/api/v2/task/{task_id}/field/{client_field_id}"
            
            payload = {
                "value": {
                    "add": [client_task_id],
                    "rem": []
                }
            }
            
            # 关键：创建包含 Content-Type 的头部
            headers_with_content = HEADERS.copy()
            headers_with_content["Content-Type"] = "application/json"
            
            print(f"   URL: {update_url}")
            print(f"   Payload: {json.dumps(payload, indent=2)}")
            
            try:
                # 使用 requests 直接发送，而不是 safe_api_call，因为我们需要特定的 headers
                update_res = requests.post(update_url, headers=headers_with_content, json=payload)
                print(f"📡 API response status: {update_res.status_code}")
                print(f"📡 API response content: {update_res.text}")
                
                # 记录 API 调用
                with api_lock:
                    api_call_timestamps.append(time.time())
                
                if update_res.status_code in (200, 201):
                    print(f"✅ Relationship field updated successfully!")
                    verify_relationship_update(task_id, client_field_id, client_task_id)
                else:
                    print(f"❌ Failed to update relationship field")
            except Exception as e:
                print(f"❌ Exception during update: {str(e)}")
        else:
            print(f"❌ No matching client found for: '{client_name}'")
    else:
        print(f"❌ Failed to search Customer List: {search_res.status_code}")

@app.route("/clickup-webhook", methods=["POST"])
def clickup_webhook():
    """Webhook 处理 - 终极安全版本"""
    data = request.json
    
    task_id = data.get("task_id") or (data.get("task") and data.get("task").get("id"))
    if not task_id:
        return jsonify({"error": "no_task_id"}), 400

    # Webhook 去重 - 5秒内同一个任务只处理一次
    current_time = time.time()
    with webhook_lock:
        if task_id in webhook_timestamps:
            last_time = webhook_timestamps[task_id]
            if current_time - last_time < 5:
                print(f"⏭️ 跳过重复webhook: {task_id}")
                return jsonify({"status": "skipped_duplicate"}), 200
        webhook_timestamps[task_id] = current_time
    
    print(f"🎯 处理任务: {task_id}")
    
    try:
        # 快速响应，避免超时
        res = safe_api_call(f"https://api.clickup.com/api/v2/task/{task_id}")
        if res.status_code == 200:
            task = res.json()
            list_id = task.get("list", {}).get("id")
            event_type = data.get('event', '')
            
            if list_id == "901811834458":  # Customer List
                print("🔄 处理客户列表任务")
                calculate_all_intervals(task_id)
            elif list_id == "901812062655":  # Order Record
                print("🆕 处理订单记录任务")
                handle_order_client_linking(task_id)
                
    except Exception as e:
        print(f"⚠️ Webhook处理异常: {str(e)}")
        # 仍然返回200，避免ClickUp认为webhook失败
        return jsonify({"status": "processed_with_errors"}), 200
    
    return jsonify({"status": "success"}), 200

@app.route("/")
def home():
    return "ClickUp Webhook Server running", 200

if __name__ == "__main__":
    # 保持完整的启动代码
    from dotenv import load_dotenv
    load_dotenv()
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)