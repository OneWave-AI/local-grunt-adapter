"""Build the small native Mac host around the local iframe dashboard."""
from pathlib import Path
import plistlib
import os
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent


def main():
    if sys.platform != "darwin":
        print("Native panel is available on macOS only"); return
    if not shutil.which("swiftc"):
        print("Install Xcode Command Line Tools to build the optional desktop panel"); return
    app = HERE / "Local Grunt Adapter.app" / "Contents"
    binary = app / "MacOS" / "LocalGruntPanel"
    binary.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["swiftc", "-O", str(HERE / "desktop/Panel.swift"), "-o", str(binary), "-framework", "AppKit", "-framework", "WebKit"], check=True)
    (app / "Info.plist").write_bytes(plistlib.dumps({"CFBundleExecutable": binary.name, "CFBundleIdentifier": "local.grunt.adapter.panel", "CFBundleName": "Local Grunt Adapter", "CFBundlePackageType": "APPL", "CFBundleShortVersionString": "0.5.1", "NSHighResolutionCapable": True, "NSAppTransportSecurity": {"NSAllowsLocalNetworking": True}}))
    # Finder/iCloud can attach metadata to freshly created app folders in Documents.
    for name in ("com.apple.FinderInfo", "com.apple.ResourceFork"):
        subprocess.run(["xattr", "-dr", name, str(app.parent)], capture_output=True)
    subprocess.run(["codesign", "--force", "--deep", "--sign", "-", str(app.parent)], check=True, capture_output=True)
    print("Built:", app.parent)


if __name__ == "__main__": main()
