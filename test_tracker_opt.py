import xmlrpc.client
import ssl

def test_tracker_field(url):
    print(f"Testing d.tracker_announce on {url}...")
    try:
        # Setup client (simplified from RTorrentClient for quick test)
        context = ssl._create_unverified_context()
        
        if url.startswith("scgi"):
            import socket
            import io
            class SCGITransport(xmlrpc.client.Transport):
                def __init__(self, host, port):
                    super().__init__()
                    self.scgi_host = host
                    self.scgi_port = port
                def request(self, host, handler, request_body, verbose=False):
                    headers = {
                        "CONTENT_LENGTH": str(len(request_body)),
                        "SCGI": "1",
                        "REQUEST_METHOD": "POST",
                        "REQUEST_URI": handler if handler else "/"
                    }
                    content = b""
                    for k, v in headers.items():
                        content += k.encode('ascii') + b'\0' + v.encode('ascii') + b'\0'
                    full_payload = str(len(content)).encode('ascii') + b':' + content + b',' + request_body
                    with socket.create_connection((self.scgi_host, self.scgi_port)) as sock:
                        sock.sendall(full_payload)
                        resp = sock.recv(4096*4) # Read some
                        # Hacky read for test
                        while b"</methodResponse>" not in resp:
                             chunk = sock.recv(4096)
                             if not chunk: break
                             resp += chunk
                    body = resp.decode('utf-8', errors='ignore').split("\n\n", 1)[-1]
                    if body.strip().startswith("<?xml"):
                        return self.parse_response(io.BytesIO(body.encode('utf-8')))
                    return self.parse_response(io.BytesIO(body.encode('utf-8')))
            
            from urllib.parse import urlparse
            p = urlparse(url)
            server = xmlrpc.client.ServerProxy("http://dummy", transport=SCGITransport(p.hostname, p.port))
        else:
            server = xmlrpc.client.ServerProxy(url, context=context)

        # Try multicall with d.tracker_announce
        # d.multicall2 signature: view, params...
        print("Sending multicall...")
        results = server.d.multicall2(
            "", "main",
            "d.name=", 
            "d.tracker_announce=" # Attempting this
        )
        print("Success!")
        print(f"Got {len(results)} results.")
        if results:
            print(f"First result: {results[0]}")
            
    except Exception as e:
        print(f"Failed: {e}")

if __name__ == "__main__":
    test_tracker_field("scgi://209.209.8.56:5000")
