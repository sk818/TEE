import multiprocessing

bind = "127.0.0.1:8001"
workers = min(multiprocessing.cpu_count() * 2 + 1, 4)
worker_class = "sync"
timeout = 300        # Long timeout for pipeline operations
max_requests = 1000  # Restart workers periodically to prevent memory leaks

accesslog = "/var/log/tessera/web_access.log"
errorlog = "/var/log/tessera/web_error.log"
loglevel = "info"
