"""Package only the preview server, launcher, documentation and compiled UI."""
import hashlib
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

root = Path(__file__).resolve().parent.parent
dist = root / 'frontend' / 'dist'
if not (dist / 'index.html').is_file():
    raise SystemExit('Build the dashboard first: cd frontend; npm ci; npm run build')
output = root / 'artifacts'
output.mkdir(exist_ok=True)
archive = output / 'TubeVault-0.1.0-preview.zip'
files = [root / 'Start-Preview.cmd', root / 'PREVIEW.md', root / 'scripts' / 'preview.py']
files.extend(p for p in dist.rglob('*') if p.is_file())
with ZipFile(archive, 'w', ZIP_DEFLATED) as bundle:
    for path in files:
        bundle.write(path, 'TubeVault-Preview/' + path.relative_to(root).as_posix())
checksum = hashlib.sha256(archive.read_bytes()).hexdigest()
archive.with_suffix('.sha256').write_text(checksum + '  ' + archive.name + '\n', encoding='utf-8')
print(f'Created {archive.name}: {archive.stat().st_size:,} bytes; {len(files)} files')
