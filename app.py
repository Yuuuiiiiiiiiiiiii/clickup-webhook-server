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

# 请求去重缓存
processed_tasks = {}
PROCESS_COOLDOWN = 10

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
            print(f"❌ Failed to fetch task for update: {res.status_code}")
            return False
            
        fields = res.json().get("custom_fields", [])
        
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
        
        if r.status_code == 429:
            print(f"🚫 Rate limit hit while updating {field_name}")
            return False
        elif r.status_code in (200, 201):
            print(f"✅ Updated {field_name}: {interval_text}")
            return True
        else:
            print(f"❌ Failed to update {field_name}: {r.status_code}")
            return False
        
    except Exception as e:
        print(f"❌ Error updating {field_name}: {str(e)}")
        return False

def calculate_all_intervals(task_id):
    """计算所有可能的间隔"""
    print(f"🔄 Starting interval calculation for task: {task_id}")
    
    res = requests.get(f"https://api.clickup.com/api/v2/task/{task_id}", headers=HEADERS)
    if res.status_code != 200:
        print(f"❌ Failed to fetch task: {res.status_code}")
        return
    
    task = res.json()
    fields = task.get("custom_fields", [])
    
    # 🔥 关键修复：添加字段调试信息
    field_names = [f.get("name") for f in fields]
    print(f"🔍 All custom fields: {field_names}")
    
    # 创建字段字典
    cf = {f["name"]: f for f in fields}
    
    # 获取日期字段 - 添加详细的调试信息
    t1_date = cf.get("📅 T1 Date", {}).get("value")
    t2_date = cf.get("📅 T2 Date", {}).get("value") 
    t3_date = cf.get("📅 T3 Date", {}).get("value")
    t4_date = cf.get("📅 T4 Date", {}).get("value")
    
    print(f"📅 Dates found - T1: {t1_date}, T2: {t2_date}, T3: {t3_date}, T4: {t4_date}")
    
    # 计算 Interval 1-2
    if t1_date and t2_date:
        print("🔄 Calculating Interval 1-2")
        d1 = parse_date(t1_date)
        d2 = parse_date(t2_date)
        diff_seconds = (d2 - d1).total_seconds()
        if diff_seconds >= 0:
            interval_12 = format_diff(diff_seconds)
            print(f"⏱️ Interval 1-2: {interval_12}")
            update_interval_field(task_id, "Interval 1-2", interval_12)
        else:
            print("⚠️ Negative interval 1-2, skipping")
    else:
        print("⏭️ Missing dates for Interval 1-2, clearing field")
        update_interval_field(task_id, "Interval 1-2", "")
    
    # 计算 Interval 2-3
    if t2_date and t3_date:
        print("🔄 Calculating Interval 2-3")
        d2 = parse_date(t2_date)
        d3 = parse_date(t3_date)
        diff_seconds = (d3 - d2).total_seconds()
        if diff_seconds >= 0:
            interval_23 = format_diff(diff_seconds)
            print(f"⏱️ Interval 2-3: {interval_23}")
            update_interval_field(task_id, "Interval 2-3", interval_23)
        else:
            print("⚠️ Negative interval 2-3, skipping")
    else:
        print("⏭️ Missing dates for Interval 2-3, clearing field")
        update_interval_field(task_id, "Interval 2-3", "")
    
    # 计算 Interval 3-4
    if t3_date and t4_date:
        print("🔄 Calculating Interval 3-4")
        d3 = parse_date(t3_date)
        d4 = parse_date(t4_date)
        diff_seconds = (d4 - d3).total_seconds()
        if diff_seconds >= 0:
            interval_34 = format_diff(diff_seconds)
            print(f"⏱️ Interval 3-4: {interval_34}")
            update_interval_field(task_id, "Interval 3-4", interval_34)
        else:
            print("⚠️ Negative interval 3-4, skipping")
    else:
        print("⏭️ Missing dates for Interval 3-4, clearing field")
        update_interval_field(task_id, "Interval 3-4", "")
    
    print("✅ Interval calculation completed")

def verify_relationship_update(task_id, client_field_id, expected_client_id):
    """验证关系字段更新是否成功"""
    print(f"🔍 Verifying relationship field update...")
    time.sleep(2)
    
    verify_res = requests.get(f"https://api.clickup.com/api/v2/task/{task_id}", headers=HEADERS)
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
    """处理Order Record的客户链接 - 使用正确的关系字段API格式"""
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
            print("🔄 Using correct Relationship Field API format")
            update_url = f"https://api.clickup.com/api/v2/task/{task_id}/field/{client_field_id}"
            
            # 正确的payload格式：包含add和rem数组的对象
            payload = {
                "value": {
                    "add": [client_task_id],  # 添加客户任务ID
                    "rem": []  # 移除的任务ID（空数组表示不移除任何）
                }
            }
            
            headers_with_content = HEADERS.copy()
            headers_with_content["Content-Type"] = "application/json"
            
            print(f"   URL: {update_url}")
            print(f"   Payload: {json.dumps(payload, indent=2)}")
            
            try:
                update_res = requests.post(update_url, headers=headers_with_content, json=payload)
                print(f"📡 API response status: {update_res.status_code}")
                print(f"📡 API response content: {update_res.text}")
                
                if update_res.status_code in (200, 201):
                    print(f"✅ Relationship field updated successfully!")
                    
                    # 验证更新是否成功
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
    data = request.json
    print("✅ Webhook received")
    
    task_id = data.get("task_id") or (data.get("task") and data.get("task").get("id"))
    if not task_id:
        print("❌ No task_id found")
        return jsonify({"error": "no task_id"}), 400

    # 🔥 去重检查
    current_time = time.time()
    if task_id in processed_tasks:
        last_time = processed_tasks[task_id]
        if current_time - last_time < PROCESS_COOLDOWN:
            print(f"⏭️ Skipping duplicate request for task {task_id}")
            return jsonify({"ignored": "duplicate"}), 200
    
    # 标记为正在处理
    processed_tasks[task_id] = current_time
    
    # 清理过期缓存（避免内存泄漏）
    expired_tasks = [tid for tid, t in processed_tasks.items() if current_time - t > PROCESS_COOLDOWN * 2]
    for task in expired_tasks:
        del processed_tasks[task]

    print(f"🎯 Processing task: {task_id}")
    
    # 🔥 关键修复：先尝试获取列表信息，如果失败则直接计算Interval
    try:
        # 获取任务详情来判断是哪个列表
        res = requests.get(f"https://api.clickup.com/api/v2/task/{task_id}", headers=HEADERS)
        if res.status_code == 200:
            task = res.json()
            list_id = task.get("list", {}).get("id")
            
            print(f"📋 Task from list: {list_id}")
            
            # 根据列表ID决定处理逻辑
            if list_id == "901811834458":  # Customer List
                print("🔄 Processing as Customer List task (Interval calculation)")
                calculate_all_intervals(task_id)
                
            elif list_id == "901812062655":  # Order Record List  
                print("🆕 Processing as Order Record task (Client linking)")
                handle_order_client_linking(task_id)
                
            else:
                print(f"❓ Unknown list: {list_id}, calculating intervals anyway")
                calculate_all_intervals(task_id)
        else:
            print(f"⚠️ Failed to fetch task details, calculating intervals anyway: {res.status_code}")
            calculate_all_intervals(task_id)
            
    except Exception as e:
        print(f"⚠️ Exception while processing task, calculating intervals anyway: {str(e)}")
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

