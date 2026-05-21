"""
╔══════════════════════════════════════════════════════════════╗
║     DAILY AUTH SCRIPT — Har Roz Subah Run Karo              ║
║     Automatically Railway ACCESS_TOKEN update karta hai      ║
╚══════════════════════════════════════════════════════════════╝
Run: python daily_auth.py
"""

import webbrowser
import http.server
import threading
import urllib.parse
import requests
import os
from kiteconnect import KiteConnect

# ================================================================
#  CONFIG — Railway Variables se ya yahan set karo
# ================================================================
API_KEY       = os.environ.get("API_KEY",    "zhve1lfpjxtie9rv")
API_SECRET    = os.environ.get("API_SECRET", "wr1cwi6ijdpa2phztvhbtm48z79a9jsu")

# Railway API — token auto-update ke liye
# Railway → Settings → Tokens → New Token → copy karo
RAILWAY_TOKEN      = ""   # <- Railway API token yahan daalo (ek baar)
RAILWAY_SERVICE_ID = ""   # <- Railway → worker → Settings → Service ID

# ================================================================
kite         = KiteConnect(api_key=API_KEY)
access_token = [None]
server_done  = threading.Event()

class CallbackHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        params        = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        request_token = params.get('request_token', [None])[0]

        if request_token:
            try:
                session         = kite.generate_session(request_token, api_secret=API_SECRET)
                access_token[0] = session['access_token']

                # Save locally
                with open('access_token.txt', 'w') as f:
                    f.write(access_token[0])

                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"""
                <html><body style='background:#000;color:#0f0;font-family:Arial;text-align:center;padding-top:100px'>
                <h1>Authentication Successful!</h1>
                <h2>Trading Bot Started!</h2>
                <p>Close this window and check Telegram for signals.</p>
                </body></html>
                """)

                print(f"\n{'='*55}")
                print(f"ACCESS TOKEN: {access_token[0]}")
                print(f"{'='*55}")
                print(f"\nToken saved to access_token.txt")

                # Auto update Railway variable if configured
                if RAILWAY_TOKEN and RAILWAY_SERVICE_ID:
                    update_railway_token(access_token[0])
                else:
                    print("\n⚠️  Railway auto-update not configured.")
                    print("Manual step: Railway → Variables → ACCESS_TOKEN update karo")
                    print(f"Token: {access_token[0]}")

            except Exception as e:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(f"Error: {e}".encode())
                print(f"ERROR: {e}")

        server_done.set()
        threading.Thread(target=self.server.shutdown).start()

    def log_message(self, *args):
        pass


def update_railway_token(token):
    """Update ACCESS_TOKEN in Railway environment variables"""
    try:
        url     = f"https://backboard.railway.app/graphql/v2"
        headers = {
            "Authorization": f"Bearer {RAILWAY_TOKEN}",
            "Content-Type":  "application/json"
        }
        query = """
        mutation($serviceId: String!, $name: String!, $value: String!) {
          variableUpsert(input: {
            serviceId: $serviceId,
            name: $name,
            value: $value
          })
        }
        """
        payload = {
            "query": query,
            "variables": {
                "serviceId": RAILWAY_SERVICE_ID,
                "name":      "ACCESS_TOKEN",
                "value":     token
            }
        }
        r = requests.post(url, json=payload, headers=headers, timeout=10)
        if r.status_code == 200:
            print("✅ Railway ACCESS_TOKEN auto-updated!")
            print("🚀 Bot will restart with new token automatically!")
        else:
            print(f"⚠️ Railway update failed: {r.text}")
            print(f"Manual: Railway → Variables → ACCESS_TOKEN = {token}")
    except Exception as e:
        print(f"⚠️ Railway update error: {e}")
        print(f"Manual: Railway → Variables → ACCESS_TOKEN = {token}")


if __name__ == "__main__":
    print("="*55)
    print("  KITE DAILY AUTH")
    print("  Opening browser for Zerodha login...")
    print("="*55)

    server        = http.server.HTTPServer(('127.0.0.1', 3000), CallbackHandler)
    server_thread = threading.Thread(target=server.serve_forever)
    server_thread.start()

    login_url = kite.login_url()
    print(f"Login URL: {login_url}")
    webbrowser.open(login_url)

    print("⏳ Waiting for login...")
    server_done.wait(timeout=180)
    server_thread.join(timeout=5)

    if access_token[0]:
        print("\n✅ Done! Token ready.")
        print("\n📋 NEXT STEP:")
        if not (RAILWAY_TOKEN and RAILWAY_SERVICE_ID):
            print("Railway → Variables → ACCESS_TOKEN mein yeh paste karo:")
            print(f"\n{access_token[0]}\n")
    else:
        print("❌ Auth failed or timed out.")
