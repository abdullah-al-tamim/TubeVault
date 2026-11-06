"""Keep the desktop vault outside Windows package-virtualized AppData."""
from contextlib import closing
import shutil
import sqlite3
from pathlib import Path

def migrate_legacy(source, target, secret_factory):
    """Copy a stopped legacy vault, preserving its source and protected secrets."""
    source, target = Path(source), Path(target)
    if (target / 'tubevault.db').exists():
        return
    staging = target.with_name(target.name + '-migration')
    staging.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect('file:' + (source / 'tubevault.db').as_posix() + '?mode=ro', uri=True)) as old:
        with closing(sqlite3.connect(staging / 'tubevault.db')) as new:
            old.backup(new)
        keys = ['local-password', 'desktop-key', 'oauth-client', 'google']
        keys.extend(row[0] for row in old.execute('SELECT secret_key FROM upload_sessions'))
    old_secrets, new_secrets = secret_factory(source), secret_factory(target)
    for key in keys:
        value = old_secrets.get(key)
        if value:
            new_secrets.set(key, value)
    if (source / 'inbox').exists():
        shutil.copytree(source / 'inbox', staging / 'inbox', dirs_exist_ok=True)
    # Never overwrite an existing destination. An interrupted migration is retried.
    if target.exists():
        raise RuntimeError('Destination vault exists without a database; review before migration')
    staging.rename(target)

def desktop_data_dir():
    from .auth import Secrets
    target = Path.home() / 'TubeVault' / 'data'
    if not (target / 'tubevault.db').exists():
        local = Path.home() / 'AppData' / 'Local'
        candidates = [local / 'TubeVault' / 'data']
        candidates.extend((local / 'Packages').glob('OpenAI.Codex_*/LocalCache/Local/TubeVault/data'))
        candidates = [p for p in candidates if (p / 'tubevault.db').is_file()]
        if candidates:
            # Prefer the normal installed-app location; preserve redirected history separately.
            source = candidates[0]
            from filelock import FileLock
            with FileLock(str(source / 'tubevault.lock'), timeout=0):
                migrate_legacy(source, target, Secrets)
            for index, other in enumerate(candidates):
                with closing(sqlite3.connect('file:' + (other / 'tubevault.db').as_posix() + '?mode=ro', uri=True)) as old:
                    with closing(sqlite3.connect(target / f'legacy-history-{index}.db')) as backup:
                        old.backup(backup)
    return target
