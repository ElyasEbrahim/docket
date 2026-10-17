"""Serve pg-jev's upstream mock API on 0.0.0.0 so other containers can reach it.

Upstream test/mock_api.py binds 127.0.0.1 in its __main__ block; importing it and serving its Handler on all
interfaces keeps its rules unchanged.
"""
import importlib.util
import sys
from http.server import ThreadingHTTPServer

spec = importlib.util.spec_from_file_location("mock_api", "/app/mock_api.py")
mock_api = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mock_api)

port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
print(f"pg-jev mock API on 0.0.0.0:{port} (keyless under /local/)", flush=True)
ThreadingHTTPServer(("0.0.0.0", port), mock_api.Handler).serve_forever()
