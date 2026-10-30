# Launch checklist (before making the repository public)

Written at the end of Prompt 8-2 (2026-10-30). The repository is still private; making it public is the owner's
decision and is done by the owner on GitHub (Settings > General > Danger zone > Change visibility).

## 1. Git history scan (done 2026-10-30, re-run just before the switch)

Everything ever committed becomes public, not only the current files.

| What | Found | Action |
|---|---|---|
| Personal paths with the Windows user name | one: `tests/data/plate_with_hole.igs` header line 4 has the author field `dhanw` (written by the CAD program that exported the IGES file) | harmless (a user name, no path); remove only if you prefer: re-export the file or edit the header, then it still exists in history unless the history is rewritten |
| Secrets (API keys, tokens, passwords) | none (patterns `api_key=`, `secret=`, `token=`, `password=`, `sk-...`, `AKIA...`, `ghp_...` over the whole history) | none |
| Large binaries (> 1 MB) | only the two example projects (`examples/Sod...`, `examples/N2 nozzle...`, 1.1 MB each) | fine |
| Design files (psd, ai, fig, docx, pptx, xlsx, zip, exe, msi, pdf) | none ever committed | none |
| Commit author email | all commits: `dhanwin3@gmail.com` | it becomes public with the repository. To hide it for future commits, use GitHub's no-reply address (Settings > Emails > "Keep my email address private") and `git config user.email <id>+<name>@users.noreply.github.com`; past commits keep the old address unless the history is rewritten |
| Uncommitted local changes | `assets/logo.png` is modified and not committed | decide whether the new logo goes in |

Commands to re-run the scan:

```bash
git rev-list --all | xargs git grep -l "dhanw"
git log -p --all | grep -iE "(api[_-]?key|secret|token|password)\s*[=:]"
git rev-list --objects --all | git cat-file --batch-check='%(objecttype) %(objectname) %(objectsize) %(rest)' | awk '$1=="blob" && $3>1000000'
git log --all --format="%ae" | sort | uniq -c
```

## 2. GPL source rule for the installer

AeroFlowSim is GPL-3.0-or-later. Whoever gives someone the installer must also offer the corresponding source code
(GPL-3.0 section 6). With a public repository this is met by:
- every GitHub release that carries the installer also has the source of the same tag (GitHub adds the source zip
  automatically) and the release notes link the tag;
- the installer shows the licence (`LICENSE`) and the third-party licences (Help > Third-party licences: Qt / PySide6
  LGPL, VTK BSD, Gmsh GPL, Numba and llvmlite BSD-2, NumPy / SciPy BSD, matplotlib PSF-style);
- Gmsh is GPL: bundling it is compatible with AeroFlowSim's GPL, its source is at the Gmsh project (name the version).

## 3. Clean-machine install test (a PC or virtual machine with no Python and no project folder)

1. Build: `python tools/build_installer.py` (PyInstaller + Inno Setup) on the development machine.
2. Copy `AeroFlowSim-<version>-setup.exe` to the clean machine; run it (SmartScreen will warn: not code-signed).
3. Start AeroFlowSim from the Start menu. Check: the window opens, no error dialog, Help > About shows the version.
4. Open the example project "N2 nozzle" from the start page; go to Results: the stored result is shown.
5. Press Run (Start from scratch): the first run compiles the Numba kernels (about 20-40 s; the Messages panel says so),
   then converges. Note the wall time.
6. Close and start AeroFlowSim again; run again: no compile delay this time (the kernel cache works). If it compiles
   every time, the cache folder is not writable in the install location (kernels.CACHE False): record it.
7. Open "Mach 2 wedge" and "NACA 0012 transonic"; run each.
8. Tools > Preferences: set 2 threads; run again; the Run step says "2 threads".
9. Help > Copy diagnostic info: paste it into a text file and keep it with the test record.
10. Uninstall from Windows Settings > Apps. Check that `%LOCALAPPDATA%\Programs\AeroFlowSim` is gone; the user's
    projects in Documents stay (expected).

## 4. Before the switch

- [ ] Latest full validation report all PASS (`validation/report.md`), CI green on main.
- [ ] README: install, screenshots, how to cite, licence badge.
- [ ] CONTRIBUTING and an issue template (optional).
- [ ] Tag and pre-release exist with the installer (Prompt 8-2 release gate).
- [ ] Re-run section 1 on the final main.
