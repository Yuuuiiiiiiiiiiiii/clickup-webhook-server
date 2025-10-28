from flask import Flask, request, jsonify
import requests
import os
import json
import time
from datetime import datetime, timezone
from dotenv import load_dotenv
from collections import deque

load_dotenv()

app = Flask(__name__)

CLICKUP_TOKEN = os.getenv("CLICKUP_TOKEN")
HEADERS = {"Authorization": CLICKUP_TOKEN}

# 请求去重缓存 & 上次日期 signature 缓存
processed_tasks = {}  # task_id -> last_processed_time (seconds)
last_date_signature = {}  # task_id -> (t1_ts, t2_ts, t3_ts, t4_ts)

PROCESS_COOLDOWN = 3  # 缩短去重时间（秒）

# ### NEW: 全局 API 调用时间戳队列，用于速率限制（滑动时间窗）
api_call_timestamps = deque()  # store epoch seconds of recent API calls
API_RATE_LIMIT = 100  # ClickUp default
API_WINDOW_SECONDS = 60
API_THROTTLE_SAFE = 90  # 当接近此阈值时慢下来

# 常量 list id
CUSTOMER_LIST_ID = "901811834458"
ORDER_RECORD_LIST_ID = "901812062655"

def now_ts():
    return time.time()

# ### NEW: rate limit helper (simple sliding window)
def ensure_rate_limit():
    """
    Ensure we don't exceed ClickUp API rate limit.
    If we are too close to the limit, sleep a small amount.
    """
    cur = now_ts()
    # drop old timestamps
    while api_call_timestamps and api_call_timestamps[0] < cur - API_WINDOW_SECONDS:
        api_call_timestamps.popleft()

    used = len(api_call_timestamps)
    if used >= API_RATE_LIMIT:
        # We've hit the limit (this is rare if we throttle earlier) - sleep until reset
        reset_in = API_WINDOW_SECONDS - (cur - api_call_timestamps[0]) + 0.1
        print(f"⚠️ Rate limit reached. Sleeping {reset_in:.2f}s")
        time.sleep(reset_in)
    elif used >= API_THROTTLE_SAFE:
        # approaching limit: back off lightly
        backoff = 1.0
        print(f"⚠️ Approaching rate limit ({used}/{API_RATE_LIMIT}). Backing off {backoff}s")
        time.sleep(backoff)

def record_api_call():
    api_call_timestamps.append(now_ts())

# ### NEW: wrapper for ClickUp GET/POST
def clickup_get(url, params=None):
    ensure_rate_limit()
    try:
        r = requests.get(url, headers=HEADERS, params=params, timeout=20)
        record_api_call()
        return r
    except Exception as e:
        print(f"❌ clickup_get exception: {e}")
        raise

def clickup_post(url, json_data=None):
    ensure_rate_limit()
    headers = HEADERS.copy()
    headers["Content-Type"] = "application/json"
    try:
        r = requests.post(url, headers=headers, json=json_data, timeout=20)
        record_api_call()
        return r
    except Exception as e:
        print(f"❌ clickup_post exception: {e}")
        raise

def parse_date(timestamp):
    # timestamp may already be int or string (ms)
    try:
        return datetime.fromtimestamp(int(timestamp) / 1000, tz=timezone.utc)
    except Exception:
        return None

def format_diff(diff_seconds):
    days = int(diff_seconds // 86400)
    hours = int((diff_seconds % 86400) // 3600)
    minutes = int((diff_seconds % 3600) // 60)
    return f"{days}d {hours}h {minutes}m"

# ### NEW: helper to directly update interval field by field id (avoid extra GET)
def update_interval_field_by_id(task_id, field_id, interval_text):
    url = f"https://api.clickup.com/api/v2/task/{task_id}/field/{field_id}"
    data = {"value": interval_text}
    r = clickup_post(url, json_data=data)
    if r.status_code in (200, 201):
        return True
    else:
        print(f"❌ Failed to update field_id {field_id} for task {task_id}: {r.status_code} {r.text}")
        return False

# ### MODIFIED: improved calculate_all_intervals which reuses task JSON and avoids extra GET
def calculate_all_intervals(task):
    """
    task: full task JSON (already fetched)
    Only calculate when date fields changed (handled outside).
    This function will:
      - find date custom fields and their values (timestamp)
      - find interval custom field ids
      - compute and update Interval 1-2 / 2-3 / 3-4 accordingly
    """
    task_id = task.get("id")
    if not task_id:
        return

    fields = task.get("custom_fields", [])

    # Map name -> (id, value)
    field_map = {}
    for f in fields:
        field_map[f.get("name", "")] = {
            "id": f.get("id"),
            "value": f.get("value")
        }

    # Keep exact emoji names
    t1_val = field_map.get("📅 T1 Date", {}).get("value")
    t2_val = field_map.get("📅 T2 Date", {}).get("value")
    t3_val = field_map.get("📅 T3 Date", {}).get("value")
    t4_val = field_map.get("📅 T4 Date", {}).get("value")

    # Convert timestamps to datetime for calculation
    d1 = parse_date(t1_val) if t1_val else None
    d2 = parse_date(t2_val) if t2_val else None
    d3 = parse_date(t3_val) if t3_val else None
    d4 = parse_date(t4_val) if t4_val else None

    # Find interval field ids
    interval_12_id = field_map.get("Interval 1-2", {}).get("id")
    interval_23_id = field_map.get("Interval 2-3", {}).get("id")
    interval_34_id = field_map.get("Interval 3-4", {}).get("id")

    # Compute and update; if not enough dates, set to empty string
    # Interval 1-2
    if d1 and d2:
        diff_seconds = (d2 - d1).total_seconds()
        if diff_seconds >= 0:
            interval_12 = format_diff(diff_seconds)
        else:
            interval_12 = ""
    else:
        interval_12 = ""

    if interval_12_id:
        update_interval_field_by_id(task_id, interval_12_id, interval_12)

    # Interval 2-3
    if d2 and d3:
        diff_seconds = (d3 - d2).total_seconds()
        if diff_seconds >= 0:
            interval_23 = format_diff(diff_seconds)
        else:
            interval_23 = ""
    else:
        interval_23 = ""

    if interval_23_id:
        update_interval_field_by_id(task_id, interval_23_id, interval_23)

    # Interval 3-4
    if d3 and d4:
        diff_seconds = (d4 - d3).total_seconds()
        if diff_seconds >= 0:
            interval_34 = format_diff(diff_seconds)
        else:
            interval_34 = ""
    else:
        interval_34 = ""

    if interval_34_id:
        update_interval_field_by_id(task_id, interval_34_id, interval_34)

    # Update last_date_signature cache (store raw timestamps or None)
    # Using ms timestamps as str to be stable
    sig = (
        str(t1_val) if t1_val else None,
        str(t2_val) if t2_val else None,
        str(t3_val) if t3_val else None,
        str(t4_val) if t4_val else None,
    )
    last_date_signature[task_id] = sig

    print(f"✅ Intervals updated for {task_id}: 1-2='{interval_12}', 2-3='{interval_23}', 3-4='{interval_34}'")

# Order Record 部分保持原样（内部实现不动）但我们會確保僅在 taskCreated 時呼叫
def verify_relationship_update(task_id, client_field_id, expected_client_id):
    """验证关系字段更新是否成功"""
    print(f"🔍 Verifying relationship field update...")
    time.sleep(2)
    
    verify_res = clickup_get(f"https://api.clickup.com/api/v2/task/{task_id}")
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
    """处理Order Record的客户链接"""
    print(f"🔗 Processing client linking for Order Record: {task_id}")
    
    res = clickup_get(f"https://api.clickup.com/api/v2/task/{task_id}")
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
    
    search_url = f"https://api.clickup.com/api/v2/list/{CUSTOMER_LIST_ID}/task"
    params = {"archived": "false"}
    search_res = clickup_get(search_url, params=params)
    
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
            
            # 在写入之前检查目标关系是否已包含该 client_task_id（避免 ping-pong）
            # 先 fetch current task custom field values (we already have task from earlier)
            # 使用正确的关系字段API格式
            print("🔄 Using correct Relationship Field API format")
            update_url = f"https://api.clickup.com/api/v2/task/{task_id}/field/{client_field_id}"
            
            payload = {
                "value": {
                    "add": [client_task_id],
                    "rem": []
                }
            }
            
            # Before posting, check if client already exists in that field to avoid duplicate writes
            # We can inspect the matched field in task's fields
            existing_vals = None
            for f in fields:
                if f.get("id") == client_field_id:
                    existing_vals = f.get("value")
                    break
            already_linked = False
            if existing_vals:
                if isinstance(existing_vals, list) and len(existing_vals) > 0:
                    # existing_vals may be list of dicts or list of ids
                    first = existing_vals[0]
                    if isinstance(first, dict):
                        if first.get("id") == client_task_id:
                            already_linked = True
                    else:
                        if first == client_task_id:
                            already_linked = True

            if already_linked:
                print(f"⏭️ Client {client_task_id} already linked — skipping write.")
                return

            headers_with_content = HEADERS.copy()
            headers_with_content["Content-Type"] = "application/json"
            
            print(f"   URL: {update_url}")
            print(f"   Payload: {json.dumps(payload, indent=2)}")
            
            try:
                # use clickup_post wrapper to respect rate limiting
                update_res = clickup_post(update_url, json_data=payload)
                print(f"📡 API response status: {update_res.status_code}")
                print(f"📡 API response content: {update_res.text}")
                
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
    data = request.json
    print("✅ Webhook received")
    
    # Extract task_id robustly
    task_id = data.get("task_id") or (data.get("task") and data.get("task").get("id"))
    if not task_id:
        print("❌ No task_id found")
        return jsonify({"error": "no task_id"}), 400

    # Basic de-dup by time to prevent immediate duplicates
    current_time = now_ts()
    if task_id in processed_tasks:
        last_time = processed_tasks[task_id]
        if current_time - last_time < PROCESS_COOLDOWN:
            print(f"⏭️ Skipping duplicate request for task {task_id} (cooldown)")
            return jsonify({"ignored": "duplicate"}), 200
    processed_tasks[task_id] = current_time

    # Try to determine event type from payload (best-effort)
    event = None
    for key in ("event", "event_type", "hook_event", "webhook_event", "action"):
        if key in data:
            event = data.get(key)
            break
    event_str = str(event).lower() if event else ""

    print(f"🎯 Processing task: {task_id}  (event: {event})")

    try:
        # Fetch full task JSON ONCE (we need fields to decide triggers)
        res = clickup_get(f"https://api.clickup.com/api/v2/task/{task_id}")
        if res.status_code != 200:
            print(f"⚠️ Failed to fetch task details: {res.status_code}")
            return jsonify({"error": "fetch_task_failed"}), 500

        task = res.json()
        list_id = task.get("list", {}).get("id")
        print(f"📁 List ID: {list_id}")

        # -------- Customer List logic: only on taskUpdated when date fields changed/assigned ------
        if list_id == CUSTOMER_LIST_ID:
            # Determine current date values (raw timestamp strings or None)
            fields = task.get("custom_fields", [])
            def get_field_value(name):
                for f in fields:
                    if f.get("name", "") == name:
                        return f.get("value")
                return None

            cur_t1 = get_field_value("📅 T1 Date")
            cur_t2 = get_field_value("📅 T2 Date")
            cur_t3 = get_field_value("📅 T3 Date")
            cur_t4 = get_field_value("📅 T4 Date")

            cur_sig = (str(cur_t1) if cur_t1 else None,
                       str(cur_t2) if cur_t2 else None,
                       str(cur_t3) if cur_t3 else None,
                       str(cur_t4) if cur_t4 else None)

            prev_sig = last_date_signature.get(task_id)

            # If prev_sig is None, treat prev as all None (so new non-empty dates are considered assigned)
            # We ONLY proceed when at least one of the four date fields was newly set (prev None -> cur not None)
            newly_assigned = False
            if prev_sig is None:
                # If this is first time we see the task, consider newly assigned any non-empty cur fields
                newly_assigned = any([cur_sig[i] is not None for i in range(4)])
            else:
                for i in range(4):
                    if prev_sig[i] is None and cur_sig[i] is not None:
                        newly_assigned = True
                        break

            # But we must ensure that at least one pair exists to compute an interval:
            # i.e., if only T1 exists (and nothing else), we should NOT act
            pair_exists = False
            if cur_sig[0] and cur_sig[1]:
                pair_exists = True
            if cur_sig[1] and cur_sig[2]:
                pair_exists = True
            if cur_sig[2] and cur_sig[3]:
                pair_exists = True

            if newly_assigned and pair_exists:
                print("🔄 Detected new date assignment AND at least one computable pair -> calculating intervals")
                # Calculate and write intervals (function will update last_date_signature)
                calculate_all_intervals(task)
            else:
                print("⏭️ No relevant date assignment detected or no computable pair -> skipping interval calc")
                # Update signature cache so we don't repeatedly treat same state as new (helps first-seen)
                last_date_signature[task_id] = cur_sig

        # -------- Order Record logic: ONLY on taskCreated event (not on update) --------
        elif list_id == ORDER_RECORD_LIST_ID:
            # Only perform linking when event indicates creation
            # ClickUp event strings may vary; just check substring 'created' or exact 'taskCreated'
            if "create" in event_str or "taskcreated" in event_str:
                print("🆕 Processing as Order Record task (Client linking) - taskCreated event")
                handle_order_client_linking(task_id)
            else:
                print("⏭️ Order Record event is not creation -> skipping linking")

        else:
            print(f"❓ Unknown list: {list_id}, skipping")
    except Exception as e:
        print(f"⚠️ Exception while processing task: {e}")
        import traceback
        traceback.print_exc()

    return jsonify({"success": True}), 200

@app.route("/")
def home():
    return "ClickUp Webhook Server running", 200

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
