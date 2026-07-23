"""
Build the app into a distributable package (name/version read from app_info.json).

Steps:
  1. Generate ICO from SVG (svg_to_ico — supersampled multi-resolution)
  2. Run PyInstaller (--onedir mode) to create the exe
  3. Sign the exe with self-signed certificate (optional — skipped if no cert)
  4. Call NSIS to create the installer (optional — skipped if makensis missing)
  5. Sign the installer with the same certificate (optional)

Graceful degradation: signing and the NSIS installer are BEST EFFORT. A
missing certificate, missing signtool.exe, or missing makensis.exe prints a
clear warning and is SKIPPED — the PyInstaller onedir output is always
produced so the build never dies just because the optional Windows-only
tooling is not installed on this machine.

Prerequisites:
  - pip install pyinstaller pillow
  - Run create_cert.py once (for code signing, optional)
  - Install NSIS (https://nsis.sourceforge.io/) and add to PATH (optional)

Usage:
    python setup/build.py
"""

import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

# -- Paths ---------------------------------------------------------
SETUP_DIR = Path(__file__).parent
PROJECT_DIR = SETUP_DIR.parent
DIST_DIR = PROJECT_DIR / "dist"
BUILD_DIR = PROJECT_DIR / "build"

# The brand mark ships as assets/logo.svg; svg_to_ico renders it to icon.ico.
SVG_PATH = PROJECT_DIR / "assets" / "logo.svg"
ICON_PATH = PROJECT_DIR / "assets" / "icon.ico"
PASSWORD_PATH = SETUP_DIR / "cert" / "password.txt"
NSI_PATH = SETUP_DIR / "installer.nsi"
APP_INFO_PATH = SETUP_DIR / "app_info.json"
COMPANY_JSON_PATH = PROJECT_DIR.parent.parent / "company.json"
VERSION_INFO_PATH = SETUP_DIR / "version_info.txt"


def _load_password() -> str:
    if not PASSWORD_PATH.exists():
        raise FileNotFoundError(
            f"Password file not found: {PASSWORD_PATH}\n"
            "Create setup/cert/password.txt with the certificate password."
        )
    return PASSWORD_PATH.read_text(encoding="utf-8").strip()


def _load_app_info() -> dict:
    return json.loads(APP_INFO_PATH.read_text(encoding="utf-8"))


def _load_company() -> dict:
    return json.loads(COMPANY_JSON_PATH.read_text(encoding="utf-8"))


APP_INFO = _load_app_info()
COMPANY = _load_company()
APP_NAME = APP_INFO["name"]
CERT_PATH = SETUP_DIR / "cert" / f"{APP_NAME}.pfx"
ENTRY_POINT = PROJECT_DIR / "main.py"


def _version_tuple(version: str) -> tuple[int, int, int, int]:
    parts = version.split(".")
    nums = [int(p) for p in parts]
    while len(nums) < 4:
        nums.append(0)
    return tuple(nums[:4])


def generate_version_info():
    step("0/5  Generating version_info.txt from app_info.json")

    v = APP_INFO["version"]
    vt = _version_tuple(v)

    content = f"""\
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={vt},
    prodvers={vt},
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable(
        u'040904B0',
        [StringStruct(u'CompanyName', u'{COMPANY["company_name"]}'),
         StringStruct(u'FileDescription', u'{APP_INFO["description"]}'),
         StringStruct(u'FileVersion', u'{v}'),
         StringStruct(u'InternalName', u'{APP_INFO["name"]}'),
         StringStruct(u'LegalCopyright', u'{COMPANY["copyright_string"]}'),
         StringStruct(u'OriginalFilename', u'{APP_INFO["exe_name"]}'),
         StringStruct(u'ProductName', u'{APP_INFO["name"]}'),
         StringStruct(u'ProductVersion', u'{v}')])
      ]),
    VarFileInfo([VarStruct(u'Translation', [0x0409, 1200])])
  ]
)
"""
    VERSION_INFO_PATH.write_text(content, encoding="utf-8")
    print(f"  Written: {VERSION_INFO_PATH}")
    print(f"  Version: {v}  Company: {COMPANY['company_name']}")


def step(msg: str):
    print(f"\n{'='*60}")
    print(f"  {msg}")
    print(f"{'='*60}")


def run(cmd: list[str], mask: str | None = None, **kwargs):
    """Run a command, print it, and check for errors.

    stdout is left inherited so long-running tools (PyInstaller, NSIS)
    still stream their progress live to the console. stderr is captured
    so a failure can print the real error instead of a silent None.

    If `mask` is given, any cmd argument equal to it (e.g. a certificate
    password) is replaced with '***' in the printed command line — the
    real value is still passed to the process.
    """
    printable = ["***" if mask is not None and str(c) == mask else str(c) for c in cmd]
    print(f"  > {' '.join(printable)}")
    result = subprocess.run(cmd, stderr=subprocess.PIPE, text=True, **kwargs)
    if result.returncode != 0:
        print(f"  FAILED (exit code {result.returncode})")
        if result.stderr:
            print(f"  {result.stderr}")
        sys.exit(1)
    return result


def generate_ico():
    step("1/5  Generating ICO from SVG")
    run([sys.executable, str(SETUP_DIR / "svg_to_ico.py")])


def build_pyinstaller():
    step("2/5  Building exe with PyInstaller")

    # Clean previous build
    for d in [DIST_DIR, BUILD_DIR]:
        if d.exists():
            print(f"  Cleaning {d}")
            shutil.rmtree(d)

    # Packages not used at runtime.
    # NOTE: unlike the Vitals template we do NOT exclude numpy or tkinter —
    # PromptPainter needs numpy/scipy (bg remover) and tkinter (the GUI is
    # ttkbootstrap/customtkinter, both tkinter-based). Only the QtWebEngine
    # family (Chromium, ~hundreds of MB, never used) is dropped from PySide6.
    exclude_modules = [
        "setuptools",
        "pkg_resources",
        # QWebEngine = a whole Chromium, not needed (we drive the owner's
        # own Chrome over CDP, never an embedded browser).
        "PySide6.QtWebEngineWidgets",
        "PySide6.QtWebEngineCore",
        "PySide6.QtWebChannel",
        "PySide6.QtWebEngineQuick",
        "PySide6.QtQuick",
        "PySide6.QtQml",
        "PySide6.QtMultimedia",
        "PySide6.Qt3DCore",
        # Heavy libraries that live in the GLOBAL site-packages (from the
        # owner's OTHER projects) but that PromptPainter never imports —
        # PyInstaller pulls them in by transitive analysis and they blow the
        # bundle to ~2 GB. The app's real 3rd-party set is only PIL /
        # customtkinter / numpy / scipy / playwright / PySide6(QtSvg) /
        # ttkbootstrap, so all of these are safe to drop (grep-verified 0
        # imports across gui.py / main.py / painter/).
        "tensorflow", "tensorboard", "keras",
        "torch", "torchvision", "torchaudio",
        "cv2",
        "pandas", "sklearn", "scikit-learn",
        "matplotlib",
        "imageio", "imageio_ffmpeg",
        "googleapiclient", "google", "grpc", "grpcio",
        "IPython", "notebook", "jupyter",
    ]

    # Modules PyInstaller may fail to detect automatically. The GUI renders
    # its SVG button icons at runtime via QSvgRenderer (PySide6.QtSvg), so
    # QtSvg + its Qt6Svg plugin MUST be bundled or every icon falls back.
    hidden_imports = [
        "PySide6.QtCore",
        "PySide6.QtGui",
        "PySide6.QtSvg",
    ]

    # Packages with data/plugins/binaries PyInstaller's static analysis alone
    # would miss: customtkinter (its widget assets + theme JSON), ttkbootstrap
    # (theme definition JSON), and playwright (the bundled node driver that
    # backs connect_over_cdp). --collect-all pulls submodules + data + binaries.
    collect_all = [
        "customtkinter",
        "ttkbootstrap",
        "playwright",
    ]

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--onedir",
        "--name", APP_NAME,
        "--icon", str(ICON_PATH),
        "--windowed",
        # No --uac-admin: PromptPainter drives a browser over CDP; it needs
        # no elevation (root CLAUDE.md: elevate only for low-level hooks).
        "--version-file", str(VERSION_INFO_PATH),
        # Bundle the icon/logo assets (assets/icons/*, assets/logo.svg) and
        # the app/company metadata. Destination 'assets' matches how the code
        # locates them (gui.ICON_DIR = <module dir>/assets/icons).
        "--add-data", f"{PROJECT_DIR / 'assets'};assets",
        "--add-data", f"{APP_INFO_PATH};setup",
        "--add-data", f"{COMPANY_JSON_PATH};.",
    ]

    for pkg in collect_all:
        cmd.extend(["--collect-all", pkg])

    for mod in hidden_imports:
        cmd.extend(["--hidden-import", mod])

    for mod in exclude_modules:
        cmd.extend(["--exclude-module", mod])

    # Entry point (must be last)
    cmd.append(str(ENTRY_POINT))

    start = time.time()
    run(cmd)
    elapsed = time.time() - start
    print(f"  PyInstaller completed in {elapsed:.1f}s")

    exe_path = DIST_DIR / APP_NAME / f"{APP_NAME}.exe"
    if not exe_path.exists():
        print(f"  ERROR: Expected exe not found: {exe_path}")
        sys.exit(1)

    # Copy ICO to dist root so NSIS shortcuts can reference $INSTDIR\icon.ico
    dist_ico = DIST_DIR / APP_NAME / "icon.ico"
    shutil.copy2(ICON_PATH, dist_ico)
    print(f"  Copied icon.ico to {dist_ico.parent}")

    print(f"  Output: {exe_path}")
    return exe_path


def sign_file(file_path: Path) -> bool:
    """Sign a single file with the project's self-signed certificate.

    Shared by both the exe-signing and installer-signing steps so the
    signtool lookup / invocation logic exists in exactly one place.

    The certificate password is only read here — i.e. lazily, at the
    moment a signature is actually needed — so a missing setup/cert/
    folder does not abort the build before PyInstaller/NSIS even run;
    it just means the build proceeds unsigned (with a warning below).

    Returns True if signing succeeded, False if it was skipped because
    the certificate or signtool.exe could not be found.
    """
    if not CERT_PATH.exists():
        print(f"  WARNING: certificate not found: {CERT_PATH}")
        print("  Run 'python setup/create_cert.py' first to sign the build.")
        print("  Signing skipped — the build proceeds UNSIGNED.")
        return False

    # Use signtool from Windows SDK
    signtool = shutil.which("signtool")
    if not signtool:
        # Try common Windows SDK locations
        sdk_paths = [
            Path(r"C:\Program Files (x86)\Windows Kits\10\bin"),
            Path(r"C:\Program Files\Windows Kits\10\bin"),
        ]
        for sdk_base in sdk_paths:
            if sdk_base.exists():
                versions = sorted(sdk_base.glob("10.*/x64/signtool.exe"))
                if versions:
                    signtool = str(versions[-1])
                    break

    if not signtool:
        print("  WARNING: signtool.exe not found (install the Windows SDK).")
        print("  Signing skipped — the build proceeds UNSIGNED.")
        return False

    cert_password = _load_password()

    cmd = [
        signtool, "sign",
        "/f", str(CERT_PATH),
        "/p", cert_password,
        "/fd", "SHA256",
        "/tr", "http://timestamp.digicert.com",
        "/td", "SHA256",
        str(file_path),
    ]

    run(cmd, mask=cert_password)
    print(f"  Signed successfully: {file_path.name}")
    return True


def sign_exe(exe_path: Path):
    step("3/5  Signing exe with certificate")
    sign_file(exe_path)


def _powershell(script: str) -> str:
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", script],
        capture_output=True, text=True,
    )
    return result.stdout.strip()


def verify_build(exe_path: Path, installer_path: Path | None):
    """Fail-closed verification gate — the build must not silently ship
    broken metadata (missing CompanyName) or an unsigned installer.

    Runs LAST, after the exe and (optional) installer are built and
    signed, and exits 1 on any problem so a broken artifact can never
    be mistaken for a good one.
    """
    step("VERIFY  metadata + signatures (build fails if anything is missing)")
    problems = []

    info = _powershell(
        f"$v=(Get-Item '{exe_path}').VersionInfo; \"$($v.CompanyName)|$($v.FileVersion)\""
    )
    company, _, file_version = info.partition("|")
    expected_company = COMPANY["company_name"]
    if company != expected_company:
        problems.append(f"exe CompanyName is {company!r}, expected {expected_company!r}")

    expected_version = APP_INFO["version"]
    if expected_version not in file_version:
        problems.append(
            f"exe FileVersion is {file_version!r}, expected to contain {expected_version!r}"
        )

    if CERT_PATH.exists() and PASSWORD_PATH.exists():
        targets = [("exe", exe_path)]
        if installer_path is not None:
            targets.append(("installer", installer_path))
        for label, target in targets:
            status = _powershell(f"(Get-AuthenticodeSignature '{target}').Status")
            if status in ("", "NotSigned"):
                problems.append(f"{label} is NOT signed (status {status or 'missing'!r})")

    if problems:
        for p in problems:
            print(f"  FAIL: {p}")
        sys.exit(1)

    print(f"  OK: CompanyName={company!r}  FileVersion={file_version!r}")
    if CERT_PATH.exists() and PASSWORD_PATH.exists():
        print("  OK: exe + installer signed")
    else:
        print("  NOTE: signing skipped (no certificate) — installer is UNSIGNED")


def _find_makensis() -> str | None:
    makensis = shutil.which("makensis")
    if makensis:
        return makensis
    for p in (
        Path(r"C:\Program Files (x86)\NSIS\makensis.exe"),
        Path(r"C:\Program Files\NSIS\makensis.exe"),
    ):
        if p.exists():
            return str(p)
    return None


def build_installer() -> Path | None:
    """Compile the NSIS installer. Best effort.

    Returns the installer path on success, or None when the step was
    skipped (makensis not installed) or the compile failed. Neither case
    aborts the build — the onedir output from step 2 is the deliverable
    and already exists on disk by the time we get here.
    """
    step("4/5  Building installer with NSIS")

    makensis = _find_makensis()
    if not makensis:
        print("  WARNING: makensis not found — installer step skipped.")
        print("  Install NSIS from https://nsis.sourceforge.io/ to build one.")
        print("  The PyInstaller onedir build is complete and unaffected.")
        return None

    cmd = [
        makensis,
        f"/DPROJECT_DIR={PROJECT_DIR}",
        f"/DDIST_DIR={DIST_DIR}",
        f"/DSETUP_DIR={SETUP_DIR}",
        f"/DAPP_VERSION={APP_INFO['version']}",
        f"/DAPP_PUBLISHER={COMPANY['company_name']}",
        f"/DAPP_URL={COMPANY['website']}",
        str(NSI_PATH),
    ]
    print(f"  > {' '.join(cmd)}")
    # Do NOT use run() here: a makensis failure must be LOUD but must not
    # kill the whole build (the onedir already succeeded). We print the
    # error and carry on so the summary still reports the real artifact.
    result = subprocess.run(cmd, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0:
        print(f"  WARNING: makensis failed (exit code {result.returncode}).")
        if result.stderr:
            print(f"  {result.stderr}")
        print("  Installer step skipped — the onedir build is still complete.")
        return None

    installer_path = DIST_DIR / APP_INFO["installer_name"]
    if not installer_path.exists():
        print("  WARNING: makensis reported success but the installer is missing.")
        return None

    print(f"  Installer: {installer_path}")
    size_mb = installer_path.stat().st_size / (1024 * 1024)
    print(f"  Size: {size_mb:.1f} MB")

    step("5/5  Signing installer with certificate")
    sign_file(installer_path)
    return installer_path


def main():
    print(f"Building {APP_NAME}")
    print(f"Project: {PROJECT_DIR}")

    if not ENTRY_POINT.exists():
        print(f"ERROR: Entry point not found: {ENTRY_POINT}")
        sys.exit(1)

    if not SVG_PATH.exists():
        print(f"ERROR: SVG logo not found: {SVG_PATH}")
        sys.exit(1)

    generate_version_info()
    generate_ico()
    exe_path = build_pyinstaller()
    sign_exe(exe_path)
    installer_path = build_installer()

    step("BUILD COMPLETE")
    print(f"  App (onedir): {exe_path.parent}")
    print(f"  Exe:          {exe_path}")
    if installer_path is not None:
        print(f"  Installer:    {installer_path}")
    else:
        print("  Installer:    (not built — see the NSIS warning above)")
    print()

    verify_build(exe_path, installer_path)


if __name__ == "__main__":
    main()
