import requests
import os
import sys

# ---------------------------------------------------------
# 🛠️ NETWORK DIAGNOSTIC TOOL
# ---------------------------------------------------------

PROXY_URL = os.environ.get('PROXY_URL')
# PROXY_URL = "http://YOUR_PROXY_HERE" # ถ้าจะเทสในคอม ใส่ตรงนี้ได้

def test_proxy():
    print("=========================================")
    print("🕵️‍♂️ STARTING PROXY DIAGNOSTICS")
    print("=========================================")

    if not PROXY_URL:
        print("❌ No PROXY_URL found in Secrets!")
        return

    print(f"🌍 Proxy Config: {PROXY_URL[:10]}...******")
    
    proxies = {
        "http": PROXY_URL,
        "https": PROXY_URL,
    }

    # TEST 1: เช็ค IP ปัจจุบัน (ดูว่า Proxy ทำงานไหม)
    try:
        print("\n1️⃣ Checking IP Address...")
        # ยิงไปเว็บเช็ค IP (timeout 5 วินาที)
        r = requests.get("http://ifconfig.me", proxies=proxies, timeout=10)
        print(f"✅ Your Public IP is: {r.text.strip()}")
        print("   (ถ้า IP นี้ไม่ใช่ IP ของ US แสดงว่า Proxy ทำงาน)")
    except Exception as e:
        print(f"❌ Failed to get IP: {e}")

    # TEST 2: ลองเข้า Google (เช็คความเร็วเน็ต)
    try:
        print("\n2️⃣ Testing Google Connectivity...")
        r = requests.get("https://www.google.com", proxies=proxies, timeout=10)
        print(f"✅ Google Status Code: {r.status_code} (OK)")
    except Exception as e:
        print(f"❌ Failed to reach Google: {e}")

    # TEST 3: ลองเข้า OKX (บอสใหญ่)
    try:
        print("\n3️⃣ Testing OKX Connectivity...")
        headers = {'User-Agent': 'Mozilla/5.0'} # แกล้งเป็น Browser
        r = requests.get("https://www.okx.com/api/v5/public/time", proxies=proxies, headers=headers, timeout=10)
        print(f"✅ OKX Status Code: {r.status_code}")
        print(f"   Response: {r.text[:100]}...")
        
        if r.status_code == 403:
            print("🚨 Result: 403 FORBIDDEN -> Proxy นี้โดน OKX บล็อก IP ครับ")
        elif r.status_code == 200:
            print("🎉 Result: SUCCESS -> Proxy นี้ใช้ได้! กลับไปใช้โค้ดบอทเดิมได้เลย")
        else:
            print("⚠️ Result: Unknown Error")
            
    except Exception as e:
        print(f"❌ Failed to reach OKX: {e}")
        print("💀 สรุป: Proxy นี้ 'ตาย' หรือ 'ช้าเกินไป' ครับ")

if __name__ == "__main__":
    test_proxy()
