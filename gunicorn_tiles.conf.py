import multiprocessing

bind = "127.0.0.1:5125"
workers = min(multiprocessing.cpu_count() * 2, 4)
worker_class = "sync"
timeout = 60
max_requests = 5000  # Restart workers periodically

accesslog = "/var/log/tessera/tiles_access.log"
errorlog = "/var/log/tessera/tiles_error.log"
loglevel = "info"
