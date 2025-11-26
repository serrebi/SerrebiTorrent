import ctypes

path = r"C:\Users\admin\libcrypto-1_1.dll"
try:
    ctypes.CDLL(path)
    print(f"Success: {path} is 32-bit (or compatible).")
except OSError as e:
    print(f"Failed: {path} - {e}")
