import qbittorrentapi
import sys

# Credentials from config.json for 'seed' profile
url = "http://serrebiradio.com:8080"
username = "admin"
password = "Rh]7kr@eC55(Ueb5"

print(f"Connecting to {url}...")

try:
    qbt_client = qbittorrentapi.Client(host=url, username=username, password=password)
    qbt_client.auth_log_in()
    print(f"Connected. qBittorrent: {qbt_client.app.version}")
    print(f"API Version: {qbt_client.app.web_api_version}")

    torrents = qbt_client.torrents_info()
    print(f"Total Torrents: {len(torrents)}")

    state_counts = {}
    seeding_candidates = 0
    
    print("\n--- Sample Torrent States ---")
    for i, t in enumerate(torrents):
        s = t.state
        progress = t.progress * 100 # qbit returns 0.0 to 1.0
        
        state_counts[s] = state_counts.get(s, 0) + 1
        
        is_complete = (progress >= 99.9) # Allow float tolerance
        
        if is_complete:
             seeding_candidates += 1

        if i < 20: # Print first 20 to avoid spam
             print(f"Hash: {t.hash[:6]}... | Name: {t.name[:30]}... | State: '{s}' | Progress: {progress:.1f}%")

    print("\n--- State Summary ---")
    for s, count in state_counts.items():
        print(f"  {s}: {count}")

    print(f"\nTotal Complete (Candidate for Seeding): {seeding_candidates}")

except Exception as e:
    print(f"Error: {e}")
