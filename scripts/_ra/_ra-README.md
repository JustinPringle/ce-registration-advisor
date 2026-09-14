# `scripts/_ra/` — vendored from reg_advisor

Byte-identical copies of reg_advisor's engine
(<https://github.com/JustinPringle/reg_advisor>). **reg_advisor is the source of
truth.** Nothing in this folder is edited here: fix it upstream, then re-sync.

Vendored files, and where each comes from, are listed in `VENDOR.lock` together
with the upstream commit and a hash of every file. Two more copies live outside
this folder and are covered by the same lock:

| here | upstream |
|---|---|
| `scripts/_ra/programme_loader.py` | `scripts/programme_loader.py` |
| `scripts/_ra/regadvisor_engine.py` | `scripts/regadvisor_engine.py` |
| `catalogue/modules.yaml` | `catalogue/modules.yaml` |
| `programmes/civil.yaml` | `programmes/civil.yaml` |
| `programmes/augmented_civil.yaml` | `programmes/augmented_civil.yaml` |

```bash
python scripts/vendor_sync.py              # refresh from ../reg_advisor
python scripts/vendor_sync.py ~/dev/reg_advisor
python scripts/vendor_sync.py --check      # verify; exits 1 on drift
python scripts/build_explorer.py           # rebuild explorer.html
```

The copies carry no local header comment. Keeping them byte-identical is what
lets `--check` be a hash comparison, which is the only kind of drift check that
does not rot.

`catalogue/modules.yaml` is generated upstream from the ITS extract by
`scripts/build_catalogue.py`. It is the source of every module's name, credits
and level; the programme YAMLs state only where a module sits and what gates it.
`build_explorer.py` passes the path explicitly and refuses to build if the file
is absent — the loader's own fallback is silent, and a silent fallback here
would put zero-credit modules on a student-facing page.
