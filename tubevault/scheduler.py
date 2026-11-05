import threading
import time
from concurrent.futures import ThreadPoolExecutor
from sqlalchemy import select
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer
from .db import Watch, Event
from .worker import metered


class Scheduler:
    def __init__(self, db, scanner, worker):
        self.db, self.scanner, self.worker = db, scanner, worker
        self.stop = worker.stop
        self.dirty = threading.Event()
        self.observer = Observer()
        self.thread = threading.Thread(target=self.run, daemon=True)

    def start(self):
        self.worker.recover()
        owner = self
        class Handler(FileSystemEventHandler):
            def on_any_event(self, event):
                owner.dirty.set()
        with self.db.session() as s:
            for watch in s.scalars(select(Watch).where(Watch.enabled == True)):
                try:
                    self.observer.schedule(Handler(), watch.path, recursive=True)
                except OSError:
                    pass
        self.observer.start()
        self.thread.start()

    def run(self):
        last_scan, last_cost, blocked = 0, 0, False
        with ThreadPoolExecutor(max_workers=4) as pool:
            tasks = []
            while not self.stop.wait(1):
                try:
                    now = time.time()
                    if now - last_scan > 30 or self.dirty.is_set() and now - last_scan > 5:
                        self.dirty.clear()
                        self.scanner.scan(automatic=True)
                        last_scan = now
                    settings = self.db.settings()
                    if settings["pause_metered"] and now - last_cost > 60:
                        blocked, last_cost = metered(), now
                    tasks = [f for f in tasks if not f.done()]
                    if not settings["pause_metered"] or not blocked:
                        for _ in range(max(0, settings["concurrency"] - len(tasks))):
                            tasks.append(pool.submit(self.worker.step))
                except Exception as e:
                    with self.db.session() as s:
                        s.add(Event(kind="scheduler_error", message=type(e).__name__))

    def close(self):
        self.stop.set()
        self.observer.stop()
        self.observer.join()
        self.thread.join()
