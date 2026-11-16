import sys
from pathlib import Path

if __name__ == '__main__':
    if Path(sys.executable).stem.lower() == 'tubevault-pull':
        from tubevault.pulls import main
        raise SystemExit(main())
    from tubevault.desktop import entry
    entry()
