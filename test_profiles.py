from config_manager import ConfigManager
import os
import json

def test_profiles():
    print("Testing ConfigManager profiles...")
    cm = ConfigManager()
    
    # 1. Check if default profile exists
    profiles = cm.get_profiles()
    print(f"Profiles count: {len(profiles)}")
    
    if not profiles:
        print("ERROR: No profiles found. Default profile should be created automatically.")
        return

    # 2. Check structure
    for pid, p in profiles.items():
        print(f"Checking profile {pid}: {p['name']} ({p['type']})")
        if 'name' not in p or 'type' not in p or 'url' not in p:
            print(f"ERROR: Invalid profile structure for {pid}")
            return

    # 3. Check default ID
    def_id = cm.get_default_profile_id()
    print(f"Default Profile ID: {def_id}")
    
    if def_id and def_id not in profiles:
        print(f"ERROR: Default profile ID {def_id} not in profiles list!")
        return

    print("Profile tests passed.")

if __name__ == "__main__":
    test_profiles()