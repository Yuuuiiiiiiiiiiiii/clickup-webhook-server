import requests
import os
from dotenv import load_dotenv

load_dotenv()

CLICKUP_TOKEN = os.getenv("CLICKUP_TOKEN")
TEAM_ID = os.getenv("TEAM_ID")

headers = {
    "Authorization": CLICKUP_TOKEN
}

print("🔍 Checking webhook configuration...")
url = f"https://api.clickup.com/api/v2/team/{TEAM_ID}/webhook"

try:
    res = requests.get(url, headers=headers)
    
    if res.status_code == 200:
        webhooks = res.json().get("webhooks", [])
        
        if not webhooks:
            print("❌ 没有任何 webhook 配置")
        else:
            print(f"✅ 找到 {len(webhooks)} 个 webhook:")
            print("=" * 60)
            
            for i, w in enumerate(webhooks, 1):
                print(f"\n{i}. Webhook 详情:")
                print(f"   ID: {w['id']}")
                print(f"   端点: {w['endpoint']}")
                print(f"   事件: {w['events']}")
                print(f"   列表ID: {w.get('list_id', '未指定')}")
                print(f"   状态: {w.get('status', '未知')}")
                
                # 检查端点是否正确
                expected_endpoint = "https://clickup-webhook-server-xa5x.onrender.com/clickup-webhook"
                if w['endpoint'] != expected_endpoint:
                    print(f"   ❌ 端点不匹配!")
                    print(f"       当前: {w['endpoint']}")
                    print(f"       期望: {expected_endpoint}")
                else:
                    print(f"   ✅ 端点正确")
                    
    elif res.status_code == 401:
        print("❌ 认证失败 - 检查 CLICKUP_TOKEN 是否正确")
    elif res.status_code == 404:
        print("❌ 团队不存在 - 检查 TEAM_ID 是否正确")
    else:
        print(f"❌ 请求失败: {res.status_code} - {res.text}")
        
except Exception as e:
    print(f"❌ 检查过程中出错: {str(e)}")
