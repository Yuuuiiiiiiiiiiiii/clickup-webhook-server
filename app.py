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

# 全局变量跟踪API调用频率
last_api_call_time = 0
MIN_API_INTERVAL = 1.5  # 最少1.5秒间隔

def safe_api_call(api_function, *args, **kwargs):
    """安全的API调用，自动处理速率限制"""
    global last_api_call_time
    
    current_time = time.time()
    time_since_last_call = current_time - last_api_call_time
    if time_since_last_call < MIN_API_INTERVAL:
        sleep_time = MIN_API_INTERVAL - time_since_last_call
        print(f"⏳ Rate limiting: waiting {sleep_time:.1f}s before API call")
        time.sleep(sleep_time)
    
    last_api_call_time = time.time()
    return api_function(*args, **kwargs)

def parse_date(timestamp):
    return datetime.fromtimestamp(int(timestamp) / 1000, tz=timezone.utc)

def format_diff(diff_seconds):
    days = int(diff_seconds // 86400)
    hours = int((diff_seconds % 86400) // 3600)
    minutes = int((diff_seconds % 3600) // 60)
    return f"{days}d {hours}h {minutes}m"

def get_task_with_fields(task_id):
    """获取任务详情和字段信息"""
    def _get_task():
        return requests.get(f"https://api.clickup.com/api/v2/task/{task_id}", headers=HEADERS)
    
    response = safe_api_call(_get_task)
    
    if response.status_code == 429:
        print("🚫 Rate limit hit, will retry after delay")
        return None, "rate_limit"
    elif response.status_code != 200:
        print(f"❌ Failed to fetch task: {response.status_code}")
        return None, "error"
    
    task = response.json()
    fields = task.get("custom_fields", [])
    return task, fields

def update_interval_field(task_id, field_name, interval_text, fields_cache=None):
    """更新Interval字段"""
    try:
        if fields_cache is None:
            task, fields = get_task_with_fields(task_id)
            if task is None:
                return False
        else:
            fields = fields_cache
        
        # 查找Interval字段
        interval_field = None
        for field in fields:
            if field.get("name") == field_name:
                interval_field = field
                break
                
        if not interval_field:
            print(f"❌ {field_name} field not found.")
            return False

        field_id = interval_field["id"]
        
        def _update_field():
            url = f"https://api.clickup.com/api/v2/task/{task_id}/field/{field_id}"
            data = {"value": interval_text}
            return requests.post(url, headers=HEADERS, json=data)
        
        r = safe_api_call(_update_field)
        
        if r.status_code == 429:
            print(f"🚫 Rate limit while updating {field_name}, will retry later")
            return False
        elif r.status_code in (200, 201):
            print(f"✅ Updated {field_name}: {interval_text}")
            return True
        else:
            print(f"❌ Failed to update {field_name}: {r.status_code} - {r.text}")
            return False
        
    except Exception as e:
        print(f"❌ Error updating {field_name}: {str(e)}")
        return False

@app.route("/clickup-webhook", methods=["POST"])
def clickup_webhook():
    data = request.json
    print("✅ Webhook received at /clickup-webhook")

    # 获取task_id
    task_id = data.get("task_id") or (data.get("task") and data.get("task").get("id"))
    if not task_id:
        print("❌ No task_id found in payload")
        return jsonify({"error": "no task_id"}), 400

    print(f"🎯 Processing task: {task_id}")

    # 字段匹配函数
    def get_field_value(field_dict, possible_names):
        for name in possible_names:
            if name in field_dict:
                return field_dict[name].get("value")
        return None

    # 重试机制
    max_retries = 2
    retry_delay = 3

    # 初始化字段变量
    t1_date = t2_date = t3_date = t4_date = None
    t2_check = t3_check = t4_check = None
    fields_cache = None

    for attempt in range(max_retries):
        # 获取任务详情
        task, fields = get_task_with_fields(task_id)
        
        if task is None:
            if attempt < max_retries - 1:
                print(f"⏳ API call failed, waiting {retry_delay}s before retry...")
                time.sleep(retry_delay)
                continue
            else:
                print("❌ Failed to fetch task after all retries")
                return jsonify({"error": "fetch task failed"}), 200
        
        # 缓存字段信息
        if fields_cache is None:
            fields_cache = fields
        
        # 创建字段字典
        cf = {f["name"]: f for f in fields}
        
        # 获取字段值 - 使用确认能工作的字段名称
        t1_date = get_field_value(cf, ["📅 T1 Date", "T1 Date", "📅 T1 Date "])
        t2_date = get_field_value(cf, ["📅 T2 Date", "T2 Date", "📅 T2 Date "]) 
        t3_date = get_field_value(cf, ["📅 T3 Date", "T3 Date", "📅 T3 Date "])
        t4_date = get_field_value(cf, ["📅 T4 Date", "T4 Date", "📅 T4 Date "])
        t2_check = get_field_value(cf, ["✅ Touch 2", "Touch 2", "✅ Touch 2 "])
        t3_check = get_field_value(cf, ["✅ Touch 3", "Touch 3", "✅ Touch 3 "])
        t4_check = get_field_value(cf, ["✅ Touch 4", "Touch 4", "✅ Touch 4 "])

        print(f"🔍 Attempt {attempt+1}: T1={t1_date}, T2={t2_date}, T3={t3_date}, T4={t4_date}")
        print(f"🔍 Attempt {attempt+1}: T2 Check={t2_check}, T3 Check={t3_check}, T4 Check={t4_check}")

        # 检查条件
        conditions_met = False
        if t2_check and t1_date and t2_date:
            conditions_met = True
        if t3_check and t2_date and t3_date:
            conditions_met = True  
        if t4_check and t3_date and t4_date:
            conditions_met = True
            
        if conditions_met:
            print("✅ Conditions met! Proceeding with calculations...")
            break
            
        if attempt < max_retries - 1:
            print(f"⏳ Conditions not met, waiting {retry_delay}s before retry...")
            time.sleep(retry_delay)
    else:
        print("❌ No valid conditions met after all retries")
        return jsonify({"ignored": True}), 200

    # 计算并更新Intervals
    results = {}
    
    try:
        # Interval 1-2
        if t2_check and t1_date and t2_date:
            d1 = parse_date(t1_date)
            d2 = parse_date(t2_date)
            diff_seconds = (d2 - d1).total_seconds()
            
            if diff_seconds >= 0:
                interval_12 = format_diff(diff_seconds)
                success = update_interval_field(task_id, "Interval 1-2", interval_12, fields_cache)
                if success:
                    results["interval_1_2"] = interval_12
                    print(f"🎉 Updated Interval 1-2: {interval_12}")
        
        # Interval 2-3
        if t3_check and t2_date and t3_date:
            d2 = parse_date(t2_date)
            d3 = parse_date(t3_date)
            diff_seconds = (d3 - d2).total_seconds()
            
            if diff_seconds >= 0:
                interval_23 = format_diff(diff_seconds)
                success = update_interval_field(task_id, "Interval 2-3", interval_23, fields_cache)
                if success:
                    results["interval_2_3"] = interval_23
                    print(f"🎉 Updated Interval 2-3: {interval_23}")
        
        # Interval 3-4
        if t4_check and t3_date and t4_date:
            d3 = parse_date(t3_date)
            d4 = parse_date(t4_date)
            diff_seconds = (d4 - d3).total_seconds()
            
            if diff_seconds >= 0:
                interval_34 = format_diff(diff_seconds)
                success = update_interval_field(task_id, "Interval 3-4", interval_34, fields_cache)
                if success:
                    results["interval_3_4"] = interval_34
                    print(f"🎉 Updated Interval 3-4: {interval_34}")
                    
        if results:
            return jsonify({"success": True, "results": results}), 200
        else:
            return jsonify({"ignored": True, "reason": "No intervals calculated"}), 200
            
    except Exception as e:
        print(f"❌ Error in calculation: {str(e)}")
        return jsonify({"error": "calculation error"}), 500

@app.route("/")
def home():
    return "ClickUp Webhook Server running", 200

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)