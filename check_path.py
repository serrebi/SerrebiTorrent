
import sys
print(sys.path)
try:
    import cloudscraper
    print("cloudscraper found")
except ImportError:
    print("cloudscraper NOT found")
