"""
╔══════════════════════════════════════════════════════════════╗
║         DAILY AUTH SCRIPT — Har Roz Subah Run Karo          ║
╚══════════════════════════════════════════════════════════════╝
Run: python daily_auth.py
"""

import webbrowser
import http.server
import threading
import urllib.parse
from kiteconnect import KiteConnect

API_KEY = "zhve1lfpjxtie9rv"
API_SECRET = "APNA_API_SECRET_YAHAN"  # KiteAutoBot ka secret

kite = KiteConnect(api_key=API_KEY)
access_token = None

class CallbackHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        global access_token
        params = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        request_token = params.get('request_token', [None])[0]
        
        if request_token:
            try:
                session = kite.generate_session(request_token, api_secret=API_SECRET)
                access_token = session['access_token']
                
                # Save token to file
                with open('access_token.txt', 'w') as f:
                    f.write(access_token)
                
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"<h1>Authentication Successful! Token saved. Close this window.</h1>")
                print(f"\n✅ ACCESS TOKEN: {access_token}")
                print(f"✅ Token saved to access_token.txt")
                print(f"\n📝 Ab kite_trading_bot.py mein ye token paste karo:")
                print(f'ACCESS_TOKEN = "{access_token}"')
            except Exception as e:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(f"Error: {e}".encode())
        
        # Stop server after getting token
        threading.Thread(target=self.server.shutdown).start()
    
    def log_message(self, format, *args):
        pass  # Suppress logs

if __name__ == "__main__":
    print("🔐 Starting Kite Authentication...")
    
    # Start local callback server
    server = http.server.HTTPServer(('127.0.0.1', 3000), CallbackHandler)
    server_thread = threading.Thread(target=server.serve_forever)
    server_thread.start()
    
    # Open browser for login
    login_url = kite.login_url()
    print(f"🌐 Opening browser for login...")
    webbrowser.open(login_url)
    
    print("⏳ Waiting for authentication...")
    server_thread.join()
    
    if access_token:
        print("\n🎉 Authentication successful!")
        print("🚀 Now run: python kite_trading_bot.py")
