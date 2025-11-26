import requests
from requests.packages.urllib3.exceptions import InsecureRequestWarning
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

url = "https://tor.serrebiradio.com/RPC2"
print(f"Checking HEADERS for {url}...")

try:
    # allow_redirects=False is KEY to seeing where it goes
    r = requests.get(url, verify=False, allow_redirects=False)
    print(f"Status Code: {r.status_code}")
    if r.is_redirect:
        print(f"Redirect Location: {r.headers.get('Location')}")
    elif r.status_code == 401:
        print("Auth Required (Basic/Digest)")
        print(f"WWW-Authenticate: {r.headers.get('WWW-Authenticate')}")
    else:
        print("No redirect. Response content sample:")
        print(r.text[:200])
except Exception as e:
    print(f"Error: {e}")
