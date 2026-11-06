"""Windows desktop host: native WebView2 window, tray, protected auto-login and sign-in startup."""
import argparse
import hashlib
import json
import os
import secrets as random_secrets
import socket
import sys
import threading
import time
from pathlib import Path

from filelock import FileLock, Timeout
from .paths import resource_root


class DesktopHost:
    def __init__(self, data_dir, secret_store):
        self.data_dir, self.secrets = data_dir, secret_store
        self.window = None
        self.server = None
        self.tray = None
        self.exiting = False
        self.url = ''
        self.tickets = {}
        self.ticket_lock = threading.Lock()
        self.native_key = secret_store.get('desktop-key')
        if not self.native_key:
            self.native_key = random_secrets.token_urlsafe(48)
            secret_store.set('desktop-key', self.native_key)

    def ticket(self):
        value = random_secrets.token_urlsafe(32)
        with self.ticket_lock:
            self.tickets = {k: t for k, t in self.tickets.items() if t > time.time()}
            self.tickets[value] = time.time() + 60
        return value

    def consume_ticket(self, value):
        with self.ticket_lock:
            return self.tickets.pop(value, 0) > time.time()

    def show(self):
        if self.window:
            self.window.load_url(self.url + '/#desktop=' + self.ticket())
            self.window.show()
            self.window.restore()

    def choose_folder(self):
        import webview
        selected = self.window.create_file_dialog(webview.FileDialog.FOLDER)
        return selected[0] if selected else None

    def open_google(self):
        import webbrowser
        webbrowser.open('https://console.cloud.google.com/apis/credentials')

    def startup_command(self):
        import subprocess
        if getattr(sys, 'frozen', False):
            args = [sys.executable, '--background']
        else:
            args = [str(Path(sys.executable).with_name('pythonw.exe')), str(resource_root() / 'desktop_entry.py'), '--background']
        return subprocess.list2cmdline(args)

    def startup_enabled(self):
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Microsoft\Windows\CurrentVersion\Run') as key:
                value, _ = winreg.QueryValueEx(key, 'TubeVault')
                return value == self.startup_command()
        except FileNotFoundError:
            return False

    def set_startup(self, enabled):
        import winreg
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r'Software\Microsoft\Windows\CurrentVersion\Run') as key:
            if enabled:
                winreg.SetValueEx(key, 'TubeVault', 0, winreg.REG_SZ, self.startup_command())
            else:
                try:
                    winreg.DeleteValue(key, 'TubeVault')
                except FileNotFoundError:
                    pass

    def quit(self):
        self.exiting = True
        if self.tray:
            self.tray.stop()
        if self.server:
            self.server.should_exit = True
        if self.window:
            self.window.destroy()

    def closing(self):
        if not self.exiting:
            self.window.hide()
            return False

    def start_tray(self, db):
        import pystray
        from PIL import Image
        def pause(*_):
            db.configure({'paused': not db.settings()['paused']})
        self.tray = pystray.Icon('TubeVault', Image.open(resource_root() / 'assets' / 'tubevault.ico'), 'TubeVault — personal video archive',
            menu=pystray.Menu(pystray.MenuItem('Open TubeVault', lambda *_: self.show(), default=True),
                pystray.MenuItem(lambda _: 'Resume uploads' if db.settings()['paused'] else 'Pause uploads', pause),
                pystray.MenuItem('Quit TubeVault', lambda *_: self.quit())))
        threading.Thread(target=self.tray.run, daemon=True).start()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--background', action='store_true')
    parser.add_argument('--data-dir', type=Path)
    args = parser.parse_args()
    data_dir = (args.data_dir or Path(os.environ['LOCALAPPDATA']) / 'TubeVault' / 'data').resolve()
    data_dir.mkdir(parents=True, exist_ok=True)
    from .auth import Secrets
    store = Secrets(data_dir)
    lock = FileLock(str(data_dir / 'tubevault.lock'), timeout=0)
    try:
        lock.acquire()
    except Timeout:
        import httpx
        for _ in range(20):
            try:
                port = json.loads((data_dir / 'runtime.json').read_text())['port']
                if not args.background:
                    response = httpx.post(f'http://127.0.0.1:{int(port)}/api/desktop/show',
                        headers={'X-Desktop-Key': store.get('desktop-key') or ''}, timeout=3, trust_env=False)
                    response.raise_for_status()
                return
            except Exception:
                time.sleep(.5)
        raise RuntimeError('TubeVault is already starting or its background process is unresponsive.')
    try:
        from alembic import command
        from alembic.config import Config as MigrationConfig
        from .config import Config
        from .db import Database
        migrations = MigrationConfig()
        migrations.set_main_option('script_location', str(resource_root() / 'migrations'))
        migrations.attributes['database_path'] = data_dir / 'tubevault.db'
        command.upgrade(migrations, 'head')
        password = store.get('local-password')
        if not password:
            password = random_secrets.token_urlsafe(48)
            store.set('local-password', password)
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.bind(('127.0.0.1', 0))
        port = listener.getsockname()[1]
        listener.listen(128)
        config = Config(_env_file=None, data_dir=data_dir, password=password,
                        host='127.0.0.1', port=port, client_secret=data_dir / 'client_secret.json',
                        allowed_hosts='127.0.0.1,localhost', origins=f'http://127.0.0.1:{port}', secure_cookie=False)
        db = Database(data_dir / 'tubevault.db')
        host = DesktopHost(data_dir, store)
        host.url = f'http://127.0.0.1:{port}'
        from .api import create_app
        import uvicorn
        host.server = uvicorn.Server(uvicorn.Config(create_app(config, db=db, desktop=host), host='127.0.0.1', port=port,
                                                   access_log=False, log_config=None))
        server_thread = threading.Thread(target=lambda: host.server.run(sockets=[listener]), daemon=True)
        server_thread.start()
        for _ in range(200):
            if host.server.started:
                break
            if not server_thread.is_alive():
                raise RuntimeError('Local server could not start')
            time.sleep(.05)
        if not host.server.started:
            raise RuntimeError('Timed out starting the local archive')
        (data_dir / 'runtime.json').write_text(json.dumps({'port': port, 'pid': os.getpid()}))
        import webview
        host.window = webview.create_window('TubeVault', host.url + '/#desktop=' + host.ticket(),
            width=1320, height=880, min_size=(900, 640), background_color='#0c131a', hidden=args.background)
        host.window.events.closing += host.closing
        host.start_tray(db)
        webview.start(gui='edgechromium', private_mode=True)
        host.server.should_exit = True
        server_thread.join(timeout=150)
        listener.close()
    finally:
        lock.release()


def entry():
    try:
        main()
    except Exception as error:
        import ctypes
        import traceback
        diagnostic = Path(os.environ['LOCALAPPDATA']) / 'TubeVault' / 'startup-error.txt'
        diagnostic.parent.mkdir(parents=True, exist_ok=True)
        frames = traceback.extract_tb(error.__traceback__)
        diagnostic.write_text(type(error).__name__ + '\n' + '\n'.join(f'{Path(f.filename).name}:{f.lineno} {f.name}' for f in frames) + ('\nMissing module: ' + str(error.name) if isinstance(error, ModuleNotFoundError) else ''), encoding='utf-8')
        # No credential values, request URLs or exception messages in dialogs/logs.
        ctypes.windll.user32.MessageBoxW(None,
            'TubeVault could not start (' + type(error).__name__ + '). Ensure Microsoft Edge WebView2 is installed, then try again. Your archive data is retained.',
            'TubeVault startup', 0x10)
        raise
