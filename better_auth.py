import requests
import sys
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urljoin

# Disable warnings
from requests.packages.urllib3.exceptions import InsecureRequestWarning
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

def attempt_login(target_url, username, password):
    print(f"Target: {target_url}")
    s = requests.Session()
    
    # 1. Hit the target to get redirected to SSO
    print("1. Navigating to target...")
    r = s.get(target_url, verify=False) # allow_redirects=True by default
    
    # If we are already 200 OK and text is not HTML login, we might be in?
    # But RPC2 usually returns 405 Method Not Allowed on GET, or XML fault.
    if r.status_code == 200 and "XML-RPC" in r.text:
         print("ALREADY CONNECTED? Response looks like XML-RPC endpoint.")
         return s
    
    # Check if we are on a login page
    soup = BeautifulSoup(r.text, 'html.parser')
    
    # Look for login form
    # YunoHost form typically has id="login-form" or similar
    forms = soup.find_all('form')
    if not forms:
        print("No login forms found on the page.")
        print(f"Current URL: {r.url}")
        return None
        
    print(f"Found {len(forms)} forms. Analyzing...")
    
    login_form = None
    # robust heuristic for login form
    for f in forms:
        if f.find('input', {'type': 'password'}):
            login_form = f
            break
    
    if not login_form:
        print("Could not identify a password login form.")
        return None
        
    # 2. Extract inputs
    action = login_form.get('action')
    if not action:
        action = r.url
    else:
        action = urljoin(r.url, action)
        
    print(f"Login Action URL: {action}")
    
    payload = {}
    inputs = login_form.find_all('input')
    for inp in inputs:
        name = inp.get('name')
        if not name: continue
        
        if name.lower() in ['user', 'username', 'login', 'email']:
            payload[name] = username
        elif name.lower() in ['pass', 'password', 'key']:
            payload[name] = password
        else:
            # Carry over hidden tokens/csrf
            payload[name] = inp.get('value', '')
            
    print(f"Payload keys: {list(payload.keys())}")
    
    # 3. POST Credentials
    print("2. Posting credentials...")
    headers = {
        'Referer': r.url,
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'
    }
    r_post = s.post(action, data=payload, headers=headers, verify=False)
    
    print(f"Login POST Status: {r_post.status_code}")
    
    # 4. Check Success
    # YunoHost sets 'SSOwat' cookie
    if 'SSOwat' in s.cookies:
        print("SUCCESS: SSOwat cookie obtained!")
        return s
    elif any(c.name == 'yunohost_sso' for c in s.cookies):
        print("SUCCESS: found yunohost_sso cookie!")
        return s
    else:
        print("FAILURE: No auth cookies found after login.")
        # print(r_post.text[:500]) # Debug html
        return None

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python better_auth.py <user> <pass>")
        sys.exit(1)
        
    user = sys.argv[1]
    pw = sys.argv[2]
    
    # Try connecting to RPC2
    session = attempt_login("https://tor.serrebiradio.com/RPC2", user, pw)
    
    if session:
        print("--- Verifying RPC Access ---")
        # Now try RPC2
        r = session.get("https://tor.serrebiradio.com/RPC2", verify=False)
        print(f"RPC2 GET Status: {r.status_code}")
        print(f"Headers: {r.headers}")
        if r.status_code == 405:
            print("Perfect! 405 'Method Not Allowed' is expected for GET on XML-RPC.")
            print("Connection Ready.")
        elif r.status_code == 200:
            print("Got 200 OK. (Might be a web page or the endpoint)")
