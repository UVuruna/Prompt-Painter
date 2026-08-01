# Build Orchestrator

**Script:** [Build Orchestrator (script)](../build.py) ·
**Flow:** [diagram](../__flow/build.md)

## Purpose

Turns the project into a distributable, signed installer in one command
(`python setup/build.py`). Reads name/version/description from
`app_info.json` and company metadata from the monorepo root
`company.json`, then drives the full pipeline: version-info generation,
ICO rendering, PyInstaller `--onedir` build, exe signing, NSIS installer
compilation, installer signing, and a fail-closed verification gate that
`sys.exit(1)`s the build rather than ship a broken artifact.

Signing and the NSIS installer step are **best effort**: a missing
certificate, missing `signtool.exe`, or missing `makensis.exe` prints a
warning and is skipped — the PyInstaller onedir output is always
produced so the build never dies just because optional Windows-only
tooling isn't installed on this machine.

## Connections

### Uses
- [ICO Generator](svg_to_ico.md) — step 1 invokes it as a subprocess (`python setup/svg_to_ico.py`) to render `assets/icon.ico` from `assets/logo.svg`
- `app_info.json` (this folder, not documented under MD-First — plain config) — name, version, description, exe/installer file names
- root `company.json` — company_name, copyright_string, website, embedded into `version_info.txt` and passed to NSIS as publisher/URL
- `installer.nsi` (this folder, not documented under MD-First — NSIS script) — compiled by `makensis` in step 4
- `cert/{APP_NAME}.pfx` + `cert/password.txt` (gitignored, produced by [Certificate Generator](create_cert.md)) — read by `sign_file` for both signing steps

### Used by
- Nothing in the project imports `setup/` — it is a standalone tool the owner runs manually per the monorepo root build pipeline

## Functions

- `_load_password()` — reads and strips the cert password from `cert/password.txt`; raises `FileNotFoundError` with setup instructions if the file is missing
- `_load_app_info()` / `_load_company()` — parse `app_info.json` / root `company.json` into dicts (loaded once at module level into `APP_INFO` / `COMPANY`)
- `_version_tuple(version)` — splits `"X.Y.Z"` into a 4-tuple padded with zeros (Windows `VERSIONINFO` requires exactly 4 numeric parts)
- `generate_version_info()` — step 0: writes `version_info.txt`, a PyInstaller `VSVersionInfo` block embedding CompanyName, FileDescription, FileVersion, InternalName, LegalCopyright, OriginalFilename, ProductName, ProductVersion
- `step(msg)` — prints a `====` banner section header to the console
- `run(cmd, mask=None, **kwargs)` — runs a subprocess with inherited stdout (so PyInstaller/NSIS progress streams live) and captured stderr; exits 1 with the real stderr on failure; if `mask` is given, that argument (e.g. the cert password) prints as `***` while the real value still reaches the process
- `generate_ico()` — step 1: shells out to `svg_to_ico.py`
- `build_pyinstaller()` — step 2: cleans `dist/` and `build/`, runs PyInstaller `--onedir --windowed` with project-specific `--exclude-module` (unused heavy libs pulled in transitively — tensorflow, torch, cv2, pandas, matplotlib, etc. — plus the entire QtWebEngine/Chromium family), `--hidden-import` (`PySide6.QtSvg` and friends, needed for runtime SVG icon rendering but not auto-detected), and `--collect-all` (`customtkinter`, `ttkbootstrap`, `playwright` — packages with data/plugins/binaries static analysis alone would miss); copies `icon.ico` into the onedir output for NSIS shortcuts
- `sign_file(file_path) -> bool` — shared signing routine used by both the exe and the installer step: locates the cert and `signtool.exe` (PATH or the two standard Windows SDK install dirs), lazily loads the password, signs with SHA256 + a DigiCert timestamp; returns `False` (never raises) when the cert or signtool can't be found, so the caller degrades gracefully
- `sign_exe(exe_path)` — step 3: calls `sign_file` on the PyInstaller exe
- `_powershell(script) -> str` — runs a PowerShell one-liner, returns trimmed stdout (used only by `verify_build`)
- `verify_build(exe_path, installer_path)` — the fail-closed gate, run LAST: reads the exe's `VersionInfo` (CompanyName, FileVersion) via PowerShell and compares against `company.json`/`app_info.json`; when a cert is configured, also checks the Authenticode signature status of the exe and (if built) the installer; collects every mismatch and `sys.exit(1)`s if any exist, so a broken artifact can never be mistaken for a good one
- `_find_makensis() -> str | None` — locates `makensis.exe` on PATH or in the two standard NSIS install dirs
- `build_installer() -> Path | None` — step 4: compiles `installer.nsi` via `makensis` with project dir/dist dir/version/publisher/URL as `/D` defines; best effort (returns `None` with a warning if `makensis` is missing or compilation fails — deliberately does NOT use `run()`, since a makensis failure must be loud but must not kill a build whose onedir output already succeeded); on success proceeds to step 5, signing the installer via `sign_file`
- `main()` — verifies the entry point (`main.py`) and SVG logo exist, runs the pipeline in order (version info → ICO → PyInstaller → sign exe → installer+sign), prints a summary, then calls `verify_build` last
