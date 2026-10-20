"""Build on macOS only. End users receive a self-contained .app in a .dmg."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
VERSION = "10.08.0"
SOURCE_URL = f"https://github.com/ArtifexSoftware/ghostpdl-downloads/releases/download/gs10080/ghostpdl-{VERSION}.tar.xz"
SOURCE_SHA256 = "94943e3c4adb7115d132b3c28b913672f2e62e6a9d802f7e754e716b1634174a"
APP_NAME = "PDF简作"


def execute(*args, cwd=ROOT, env=None, **kw):
    subprocess.run([str(arg) for arg in args], cwd=cwd, env=env, check=True, **kw)


def prepare_engine():
    destination = ROOT / "tools" / "ghostscript"
    library = destination / "lib" / "libgs.dylib"
    marker = destination / "macos-build.json"
    expected = {"version": VERSION, "arch": platform.machine(), "source_sha256": SOURCE_SHA256}
    if library.exists() and marker.exists() and json.loads(marker.read_text()) == expected:
        return destination
    cache = ROOT / "tools" / "downloads"
    cache.mkdir(parents=True, exist_ok=True)
    archive_path = cache / f"ghostpdl-{VERSION}.tar.xz"
    if not archive_path.exists():
        urllib.request.urlretrieve(SOURCE_URL, archive_path)
    with archive_path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    if digest != SOURCE_SHA256:
        raise RuntimeError("Ghostscript source checksum mismatch; refusing to build.")
    work = ROOT / "build" / f"gs-source-{platform.machine()}"
    work.mkdir(parents=True, exist_ok=True)
    source = work / f"ghostpdl-{VERSION}"
    if not source.is_dir():
        with tarfile.open(archive_path) as archive:
            archive.extractall(work, filter="data")
    env = os.environ.copy()
    env.setdefault("MACOSX_DEPLOYMENT_TARGET", "13.0")
    # Use the source distribution's libraries; never depend on a user's Homebrew.
    env["PKGCONFIG"] = "/usr/bin/false"
    env["DARWIN_LDFLAGS_SO_PREFIX"] = "@rpath/"
    execute("./configure", "--disable-cups", "--disable-gtk", "--disable-fontconfig",
            "--disable-dbus", "--without-x", "--without-libidn", "--without-libpaper",
            "--without-tesseract", "--without-pdftoraster", "--without-pcl", "--without-xps",
            "--with-local-zlib", "--with-local-brotli", "--with-libiconv=native", "--with-drivers=PS",
            cwd=source, env=env)
    execute("make", f"-j{min(os.cpu_count() or 2, 4)}", "so", cwd=source, env=env)
    built = source / "sobin" / "libgs.dylib"
    if not built.exists(): raise RuntimeError("Ghostscript did not produce sobin/libgs.dylib")
    library.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(built.resolve(), library)
    execute("install_name_tool", "-id", "@rpath/libgs.dylib", library)
    dependencies = subprocess.check_output(["otool", "-L", str(library)], text=True).splitlines()[2:]
    for line in dependencies:
        dependency = line.strip().split(" (", 1)[0]
        if dependency and not dependency.startswith(("/usr/lib/", "/System/Library/")):
            raise RuntimeError(f"Unbundled Ghostscript dependency: {dependency}")
    for name in ("Resource", "iccprofiles", "lib"):
        shutil.copytree(source / name, destination / name, dirs_exist_ok=True)
    shutil.copy2(source / "LICENSE", destination / "COPYING")
    marker.write_text(json.dumps(expected, indent=2), encoding="utf-8")
    return destination


def self_check(app):
    executable = app / "Contents" / "MacOS" / APP_NAME
    with tempfile.TemporaryDirectory(prefix="pdf-desktop-selfcheck-") as folder:
        # Run from outside the project, hiding developer Python and external engines.
        env = os.environ.copy()
        for key in ("PYTHONPATH", "PYTHONHOME", "GS_LIB", "GS_DLL", "DYLD_LIBRARY_PATH"):
            env.pop(key, None)
        env["PATH"] = "/usr/bin:/bin:/usr/sbin:/sbin"
        execute(executable, "--self-check", folder, cwd=folder, env=env, timeout=90)
        report = json.loads((Path(folder) / "selfcheck.json").read_text(encoding="utf-8"))
        if not report.get("success") or not report.get("drag_drop_ready"):
            raise RuntimeError(f"Bundled app self-check failed: {report}")
        target = ROOT / "dist" / f"macos-{platform.machine()}-selfcheck.json"
        target.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")


def notarize(path, profile):
    execute("xcrun", "notarytool", "submit", path, "--keychain-profile", profile, "--wait")


def build():
    if sys.platform != "darwin":
        raise SystemExit("macOS App/DMG must be built on a Mac or macOS CI runner, not Windows.")
    parser = argparse.ArgumentParser()
    parser.add_argument("--sign-identity", default=os.environ.get("MACOS_SIGN_IDENTITY"))
    parser.add_argument("--notary-profile", default=os.environ.get("MACOS_NOTARY_PROFILE"))
    args = parser.parse_args()
    if args.notary_profile and not args.sign_identity:
        parser.error("Notarization requires a Developer ID signing identity.")
    engine = prepare_engine()
    command = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--onedir", "--windowed",
               "--name", APP_NAME, "--osx-bundle-identifier", "com.pdfjianzuo.desktop",
               "--target-arch", platform.machine(), "--collect-all", "customtkinter", "--collect-all", "tkinterdnd2",
               "--add-binary", f"{engine / 'lib' / 'libgs.dylib'}:ghostscript/lib"]
    for name in ("Resource", "iccprofiles", "lib"):
        # The library directory also contains PostScript helper resources.
        if name == "lib":
            for helper in (engine / name).iterdir():
                if helper.is_file() and helper.suffix != ".dylib":
                    command += ["--add-data", f"{helper}:ghostscript/lib"]
        else:
            command += ["--add-data", f"{engine / name}:ghostscript/{name}"]
    command += ["--add-data", f"{engine / 'COPYING'}:ghostscript"]
    if args.sign_identity: command += ["--codesign-identity", args.sign_identity]
    command.append("app.py")
    execute(*command)
    app = ROOT / "dist" / f"{APP_NAME}.app"
    # Never ship a package that requires Python/Ghostscript from the build machine.
    self_check(app)
    if args.sign_identity:
        execute("codesign", "--verify", "--deep", "--strict", app)
    if args.notary_profile:
        archive = ROOT / "build" / "app-for-notarization.zip"
        execute("ditto", "-c", "-k", "--keepParent", app, archive)
        notarize(archive, args.notary_profile)
        execute("xcrun", "stapler", "staple", app)
        execute("spctl", "--assess", "--type", "execute", "--verbose", app)
    suffix = "" if args.notary_profile else "-unnotarized"
    dmg = ROOT / "dist" / f"{APP_NAME}-macOS-{platform.machine()}{suffix}.dmg"
    with tempfile.TemporaryDirectory(prefix="pdf-dmg-stage-") as folder:
        stage = Path(folder)
        execute("ditto", app, stage / app.name)
        (stage / "Applications").symlink_to("/Applications")
        execute("hdiutil", "create", "-volname", APP_NAME, "-srcfolder", stage, "-ov", "-format", "UDZO", dmg)
    if args.sign_identity:
        execute("codesign", "--force", "--timestamp", "--sign", args.sign_identity, dmg)
    if args.notary_profile:
        notarize(dmg, args.notary_profile)
        execute("xcrun", "stapler", "staple", dmg)
        execute("xcrun", "stapler", "validate", dmg)
    with dmg.open("rb") as stream:
        checksum = hashlib.file_digest(stream, "sha256").hexdigest()
    dmg.with_suffix(".dmg.sha256").write_text(f"{checksum}  {dmg.name}\n", encoding="utf-8")
    print(f"Built {dmg}")


if __name__ == "__main__": build()
