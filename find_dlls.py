import os
import ctypes
import shutil

target_dir = os.path.dirname(os.path.abspath(__file__))
print(f"Scanning for 32-bit OpenSSL DLLs in C:\\Users\\admin...")

found_crypto = None
found_ssl = None

for root, dirs, files in os.walk("C:\\Users\\admin"):
    # Skip the current target dir to avoid false positive on the broken ones we copied
    if os.path.abspath(root) == os.path.abspath(target_dir):
        continue

    for file in files:
        if file.lower() == "libcrypto-1_1.dll" and not found_crypto:
            full_path = os.path.join(root, file)
            try:
                # Try loading with 32-bit python
                ctypes.CDLL(full_path)
                print(f"FOUND VALID 32-bit CRYPTO: {full_path}")
                found_crypto = full_path
            except OSError:
                pass # Not 32-bit or other error
        
        if file.lower() == "libssl-1_1.dll" and not found_ssl:
            full_path = os.path.join(root, file)
            try:
                ctypes.CDLL(full_path)
                print(f"FOUND VALID 32-bit SSL: {full_path}")
                found_ssl = full_path
            except OSError:
                pass

    if found_crypto and found_ssl:
        break

if found_crypto:
    shutil.copy(found_crypto, os.path.join(target_dir, "libcrypto-1_1.dll"))
    print("Copied libcrypto.")
else:
    print("Could not find 32-bit libcrypto-1_1.dll")

if found_ssl:
    shutil.copy(found_ssl, os.path.join(target_dir, "libssl-1_1.dll"))
    print("Copied libssl.")
else:
    print("Could not find 32-bit libssl-1_1.dll")
