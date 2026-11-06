# Build with .venv\Scripts\pyinstaller.exe packaging\TubeVault.spec
from pathlib import Path
from PyInstaller.utils.hooks import collect_all, collect_submodules
root = Path(SPECPATH).parent
web_data, web_bins, web_hidden = collect_all('webview')
data = web_data + [(str(root/'frontend'/'dist'), 'frontend/dist'), (str(root/'migrations'), 'migrations'), (str(root/'assets'), 'assets')]
a = Analysis([str(root/'desktop_entry.py')], pathex=[str(root)], binaries=web_bins, datas=data,
    hiddenimports=web_hidden + collect_submodules('keyring.backends') + collect_submodules('uvicorn') + ['pystray._win32','google.auth.transport.requests','sqlalchemy.dialects.sqlite'],
    excludes=['pytest','tkinter','IPython','matplotlib','PyQt5','PyQt6','PySide2','PySide6'])
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='TubeVault', debug=False, bootloader_ignore_signals=False,
          strip=False, upx=False, console=False, icon=str(root/'assets'/'tubevault.ico'))
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='TubeVault')
