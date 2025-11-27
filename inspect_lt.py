from libtorrent_env import prepare_libtorrent_dlls
prepare_libtorrent_dlls()

import libtorrent as lt

try:
    print(f"Libtorrent version: {lt.version}")
    
    # Check for settings_pack
    if hasattr(lt, 'settings_pack'):
        print("lt.settings_pack exists")
        # Check inside
        print(f"dir(lt.settings_pack): {[x for x in dir(lt.settings_pack) if 'proxy' in x.lower()]}")
    else:
        print("lt.settings_pack DOES NOT exist")

    # Check for proxy_type_t at top level
    if hasattr(lt, 'proxy_type_t'):
        print("lt.proxy_type_t exists")
        print(f"dir(lt.proxy_type_t): {dir(lt.proxy_type_t)}")

except Exception as e:
    print(e)