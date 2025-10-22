# app_debug_fixed.py
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

print("🚀 Server starting with enhanced debugging...")

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
    res = requests.get(f"https://api.clickup.com/api/v2/task/{task_id}", headers=HEADERS)
    if res.status_code != 200:
        print(f"❌ Failed to fetch task: {res.status_code}")
        return
    
    task = res.json()
    fields = task.get("custom_fields", [])
    
    cf = {f["name"]: f for f in fields}
    
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
        update_interval_field(task_id, "Interval 3-4", "")

def handle_order_client_linking(task_id):
    """处理Order Record的客户链接 - 详细调试版本"""
    print(f"\n🎯 ===== 开始处理客户链接: {task_id} =====")
    
    # 1. 获取任务详情
    print(f"📡 获取任务详情...")
    res = requests.get(f"https://api.clickup.com/api/v2/task/{task_id}", headers=HEADERS)
    if res.status_code != 200:
        print(f"❌ 获取任务失败: {res.status_code}")
        return
        
    task = res.json()
    fields = task.get("custom_fields", [])
    
    # 2. 查找关键字段
    client_name = None
    client_field_id = None
    
    print(f"🔍 分析字段...")
    for field in fields:
        field_name = field.get("name", "")
        field_value = field.get("value")
        field_id = field.get("id")
        
        print(f"   📋 '{field_name}': {field_value} (ID: {field_id})")
        
        # 匹配👤 Client Name字段
        if "👤 Client Name" == field_name:
            client_name = field_value
            print(f"   ✅ 找到Client Name: '{client_name}'")
            
        # 匹配👤 Client关系字段
        elif "👤 Client" == field_name:
            client_field_id = field_id
            print(f"   ✅ 找到Client关系字段ID: {client_field_id}")
    
    if not client_name:
        print("❌ 未找到Client Name字段")
        return
        
    if not client_field_id:
        print("❌ 未找到Client关系字段")
        return
    
    print(f"\n🎯 搜索客户: '{client_name}'")
    
    # 3. 在Customer List中搜索匹配的客户
    CUSTOMER_LIST_ID = "901811834458"
    
    print(f"📡 搜索Customer List中的任务...")
    search_url = f"https://api.clickup.com/api/v2/list/{CUSTOMER_LIST_ID}/task"
    params = {"archived": "false"}
    search_res = requests.get(search_url, headers=HEADERS, params=params)
    
    if search_res.status_code == 200:
        customer_tasks = search_res.json().get("tasks", [])
        print(f"📊 在Customer List中找到 {len(customer_tasks)} 个任务")
        
        # 精确匹配客户名称
        matched_task = None
        for customer_task in customer_tasks:
            customer_name = customer_task.get("name", "").strip()
            if customer_name.lower() == client_name.strip().lower():
                matched_task = customer_task
                print(f"✅ 精确匹配: '{customer_name}' -> {customer_task.get('id')}")
                break
        
        if matched_task:
            client_task_id = matched_task.get("id")
            
            # 4. 更新关系字段 - 尝试不同格式
            print(f"\n🔄 开始更新关系字段...")
            
            # 尝试格式1: 简单ID数组
            update_url = f"https://api.clickup.com/api/v2/task/{task_id}/field/{client_field_id}"
            update_data_1 = {"value": [client_task_id]}
            
            print(f"   🔄 尝试格式1: 简单ID数组")
            print(f"   📤 请求URL: {update_url}")
            print(f"   📦 请求数据: {json.dumps(update_data_1)}")
            
            update_res_1 = requests.post(update_url, headers=HEADERS, json=update_data_1)
            print(f"   📥 响应状态: {update_res_1.status_code}")
            print(f"   📥 响应内容: {update_res_1.text}")
            
            if update_res_1.status_code in (200, 201):
                print(f"   ✅ 格式1更新成功!")
            else:
                # 尝试格式2: 对象数组
                print(f"   🔄 尝试格式2: 对象数组")
                update_data_2 = {
                    "value": [
                        {
                            "id": client_task_id,
                            "name": matched_task.get("name")
                        }
                    ]
                }
                print(f"   📦 请求数据: {json.dumps(update_data_2)}")
                update_res_2 = requests.post(update_url, headers=HEADERS, json=update_data_2)
                print(f"   📥 响应状态: {update_res_2.status_code}")
                print(f"   📥 响应内容: {update_res_2.text}")
                
                if update_res_2.status_code in (200, 201):
                    print(f"   ✅ 格式2更新成功!")
                else:
                    print(f"   ❌ 两种格式都失败了")
            
            # 5. 验证更新结果
            print(f"\n🔍 验证更新结果...")
            time.sleep(2)  # 等待API处理
            
            # 验证更新是否成功
            verify_res = requests.get(f"https://api.clickup.com/api/v2/task/{task_id}", headers=HEADERS)
            if verify_res.status_code == 200:
                verify_task = verify_res.json()
                verify_fields = verify_task.get("custom_fields", [])
                for field in verify_fields:
                    if field.get("id") == client_field_id:
                        linked_value = field.get("value")
                        print(f"   🔍 Client字段当前值: {linked_value}")
                        if linked_value and len(linked_value) > 0:
                            if isinstance(linked_value[0], dict):
                                linked_id = linked_value[0].get('id')
                            else:
                                linked_id = linked_value[0]
                            print(f"   🎉 成功链接客户: {linked_id}")
                        else:
                            print(f"   ❌ Client字段仍然为空!")
                        break
            else:
                print(f"   ❌ 验证失败: {verify_res.status_code}")
                
        else:
            print(f"❌ 在Customer List中未找到匹配的客户: '{client_name}'")
            print(f"📋 Customer List中的客户:")
            for i, customer_task in enumerate(customer_tasks[:5]):
                print(f"   {i+1}. {customer_task.get('name')}")
                
    else:
        print(f"❌ 搜索Customer List失败: {search_res.status_code}")
    
    print(f"🏁 ===== 处理完成 =====\n")

@app.route("/clickup-webhook", methods=["POST"])
def clickup_webhook():
    try:
        data = request.json
        print(f"\n✅ Webhook接收时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
        
        # 获取任务ID
        task_id = data.get("task_id") or (data.get("task") and data.get("task").get("id"))
        if not task_id:
            print("❌ Webhook数据中没有task_id")
            return jsonify({"error": "no task_id"}), 400
            
        print(f"🆔 任务ID: {task_id}")
        print(f"📦 原始数据: {json.dumps(data, indent=2)}")
        
        # 去重检查
        current_time = time.time()
        if task_id in processed_tasks:
            last_time = processed_tasks[task_id]
            if current_time - last_time < PROCESS_COOLDOWN:
                print(f"⏭️ 跳过重复请求: {task_id}")
                return jsonify({"ignored": "duplicate"}), 200
        
        processed_tasks[task_id] = current_time

        # 获取任务详情来判断是哪个列表
        print(f"📡 获取任务详情...")
        res = requests.get(f"https://api.clickup.com/api/v2/task/{task_id}", headers=HEADERS)
        if res.status_code != 200:
            print(f"❌ 获取任务失败: {res.status_code}")
            return jsonify({"error": "fetch failed"}), 500
            
        task = res.json()
        list_id = task.get("list", {}).get("id")
        task_name = task.get("name", "Unknown")
        
        print(f"📋 任务名称: {task_name}")
        print(f"📁 列表ID: {list_id}")
        
        # 根据列表ID决定处理逻辑
        if list_id == "901812062655":  # Order Record List  
            print("🆕 这是Order Record任务 - 开始客户链接")
            handle_order_client_linking(task_id)
        else:
            print(f"ℹ️ 来自其他列表的任务: {list_id}")
            
        return jsonify({"success": True}), 200
        
    except Exception as e:
        print(f"💥 未预期错误: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route("/")
def home():
    return "ClickUp Webhook Debug Server Running", 200

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    port = int(os.environ.get("PORT", 10000))
    print(f"🚀 启动调试服务器，端口: {port}")
    app.run(host="0.0.0.0", port=port)