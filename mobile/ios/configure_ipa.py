"""Configure the public Google iOS client identifier before personal signing."""
import argparse
import plistlib
import re
from pathlib import Path
from zipfile import ZipFile

PLIST = "Payload/TubeVault.app/Info.plist"


def configure(source: Path, destination: Path, client: str, bundle: str):
    if not re.fullmatch(r"[a-zA-Z0-9-]+\.apps\.googleusercontent\.com", client):
        raise ValueError("Expected the public iOS OAuth client ID ending in .apps.googleusercontent.com")
    if not re.fullmatch(r"[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+", bundle):
        raise ValueError("Expected a reverse-DNS bundle identifier")
    with ZipFile(source) as archive:
        info = plistlib.loads(archive.read(PLIST))
        info.update(GoogleClientID=client, CFBundleIdentifier=bundle,
                    CFBundleURLTypes=[{"CFBundleURLSchemes": [".".join(reversed(client.split(".")))]}])
        with ZipFile(destination, "x") as output:
            for entry in archive.infolist():
                data = plistlib.dumps(info) if entry.filename == PLIST else archive.read(entry)
                output.writestr(entry, data)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ipa", type=Path)
    parser.add_argument("--client", required=True)
    parser.add_argument("--bundle", default="com.abdullahaltamim.tubevault")
    parser.add_argument("--out", type=Path, default=Path("TubeVault-personal.ipa"))
    args = parser.parse_args()
    configure(args.ipa, args.out, args.client.strip(), args.bundle)
