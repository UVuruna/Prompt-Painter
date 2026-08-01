# setup/

The build & release pipeline for the desktop app: turns the checked-out
project into a signed, distributable installer. Standalone tooling —
nothing else in PromptPainter imports this folder; the owner (or a
build session) runs its scripts directly from the command line.

## Files

| File | Tier | One line |
|------|------|----------|
| `build.py` | Algorithmic | 7-step build orchestrator — version info, ICO, PyInstaller, sign, NSIS, sign installer, fail-closed verify gate — [about](__about/build.md) · [flow](__flow/build.md) |
| `create_cert.py` | Standard | one-time self-signed code-signing certificate generator — [about](__about/create_cert.md) |
| `svg_to_ico.py` | Algorithmic | adaptive supersample + Lanczos multi-resolution ICO renderer — [about](__about/svg_to_ico.md) · [flow](__flow/svg_to_ico.md) |

Not covered by MD-First docs (non-Python build artifacts/scripts, outside
this project's doc-governance scope): `installer.nsi` — the NSIS
installer script `build.py` compiles via `makensis` (sections: main
install, optional desktop shortcut, optional autostart); `app_info.json`
— the project metadata `build.py` reads (name, version, description,
exe/installer file names); `version_info.txt` — generated fresh by
`build.py` at build time, gitignored.

## Connections

### Uses
- Root `company.json` — `company_name`, `copyright_string`, `website`; read by `build.py` for both `version_info.txt` and the NSIS publisher/URL defines
- `app_info.json` (this folder) — the single source of project metadata (name, version, description, exe/installer names) every script reads
- `assets/logo.svg` (project root `assets/`) — the only input to `svg_to_ico.py`
- `cert/` (gitignored) — the `.pfx` + `password.txt` `create_cert.py` produces and `build.py`'s `sign_file` consumes
- `main.py` (project root) — the PyInstaller entry point `build.py` bundles

### Used by
- Nothing in the project imports `setup/` — it is a standalone tool the owner runs manually (`python setup/build.py`, `python setup/create_cert.py`, `python setup/svg_to_ico.py`), per the monorepo root [CLAUDE.md](../../../CLAUDE.md) Build & Release System

## Design Decisions

- **`--onedir`, not `--onefile`.** `build_pyinstaller()` builds in
  onedir mode — lower RAM, faster startup, fewer antivirus false
  positives than a single self-extracting exe (the monorepo-wide
  convention; see root `CLAUDE.md`'s Build Pipeline).
- **Signing is one shared function, called twice.** `sign_file()` holds
  all the signtool lookup/invocation logic once; `sign_exe()` (step 3)
  and `build_installer()` (step 5) both call it, so the inner exe and
  the final installer are signed identically. This was a deliberate fix
  for the historically real failure of signing only the inner exe and
  shipping an unsigned installer — the file the user actually downloads
  and runs.
- **Signing and the NSIS installer are BEST EFFORT, never fatal.** A
  missing certificate, missing `signtool.exe`, or missing
  `makensis.exe` prints a warning and is skipped. The PyInstaller
  onedir output is always produced, so the build never dies just
  because optional Windows-only tooling isn't installed on the
  machine running it.
- **The cert password is loaded lazily, inside `sign_file`.** Not at
  module import time — so a missing `setup/cert/` folder doesn't abort
  the whole build before PyInstaller or NSIS even run; it just means
  the build proceeds unsigned.
- **`verify_build()` runs last and is fail-closed, not best-effort.**
  Every step before it can fail *silently* — PyInstaller without a
  version file still produces an exe (just with an empty CompanyName),
  a skipped signing step just yields an unsigned file — and the build
  would otherwise return exit 0 while shipping a broken artifact.
  `verify_build` asserts on the actual OUTPUT (exe metadata via
  PowerShell `VersionInfo`, Authenticode signature status when a cert
  is configured) and calls `sys.exit(1)` if anything doesn't match, so
  a broken artifact can never be mistaken for a good one.
- **`create_cert.py` never overwrites an existing certificate.** If
  `cert/{APP_NAME}.pfx` already exists, `create_certificate()` prints a
  message and returns — regenerating requires deleting the old `.pfx`
  by hand first, so a re-run can never silently invalidate a
  certificate already trusted somewhere.
- **`svg_to_ico.py` supersamples small sizes.** A direct SVG render at
  16px or 32px looks visibly soft; rendering at up to 4x the target
  size and Lanczos-downscaling keeps small icon frames sharp. The
  factor tapers off as target size grows (4x → 2x → 1x) since larger
  targets already have enough native pixels.
