#!/usr/bin/env bash
# merge-aug_fix.sh -- merge aug_fix into feature/single-source-local-folder.
#
# Run from the repo root of ce-registration-advisor. Stop on the first error;
# nothing here is destructive until the final commit, and `git merge --abort`
# backs the whole thing out.
#
# The two branches forked from 5497cf3 and neither knows about the other, so
# git offers conflicts in nine files. Only two of them are a real merge. The
# rest are decided by a rule, not by reading diffs:
#
#   vendored from reg_advisor -> take aug_fix (it is the newer sync of the same
#                                upstream; the feature branch's copies are an
#                                older snapshot of identical work)
#   generated                 -> take neither, rebuild
#   editor/build noise        -> delete and .gitignore it
#
set -euo pipefail

FEATURE=feature/single-source-local-folder
REG_ADVISOR=${REG_ADVISOR:-../reg_advisor}

git checkout "$FEATURE"
git pull --ff-only
git merge --no-commit --no-ff aug_fix || true    # conflicts are expected

# --- 1. Vendored files: aug_fix wins outright ---------------------------------
# These are byte copies of reg_advisor@backend_dev 8829e1f. The feature branch
# carries the same upstream work at an earlier point (choice groups, the twin
# map, gpa_passed); aug_fix carries that PLUS the module catalogue, the
# catalogue_overrides block and the derived preceding_core gate. Superset, so
# "theirs" is a strict gain, not a loss.
git checkout --theirs \
  programmes/civil.yaml \
  programmes/augmented_civil.yaml \
  scripts/_ra/programme_loader.py \
  scripts/ra_engine.js
git add \
  programmes/civil.yaml \
  programmes/augmented_civil.yaml \
  scripts/_ra/programme_loader.py \
  scripts/ra_engine.js
# regadvisor_engine.py, catalogue/modules.yaml, vendor_sync.py, VENDOR.lock and
# the _ra README merge on their own.

# --- 2. Noise that should never have been tracked -----------------------------
git rm -q --cached --ignore-unmatch \
  .DS_Store scripts/.DS_Store scripts/_ra/.DS_Store \
  ce_advisory/.DS_Store ce_advisory/catalogue/.DS_Store \
  single-source-local-folder.patch \
  $(git ls-files | grep -F '__pycache__' || true)
find . -name .DS_Store -delete
find . -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null || true
rm -f single-source-local-folder.patch

# --- 3. The two hand-merged files + .gitignore --------------------------------
# Copy the three attached files over the conflicted ones, then stage them:
#   scripts/build_explorer.py        (union of both branches' edits)
#   scripts/explorer_template.html   (your UX work + the gpa_passed reads)
#   .gitignore
echo
echo ">>> Copy the three attached files into place now, then press Enter."
read -r _
git add scripts/build_explorer.py scripts/explorer_template.html .gitignore

# --- 4. Rename the vendor README to its proper name ---------------------------
[ -f scripts/_ra/_ra-README.md ] && git mv scripts/_ra/_ra-README.md scripts/_ra/README.md

# --- 5. explorer.html is generated. Rebuild rather than merge ------------------
python3 scripts/vendor_sync.py --check "$REG_ADVISOR"
python3 scripts/build_explorer.py
git add explorer.html

git status --short
echo
echo "No 'UU' or 'AA' lines above means the merge is resolved."
echo "Open explorer.html: the footer parity chip should read 510/510, green."
echo "Then:  git commit -m 'Merge aug_fix: module catalogue + vendor sync'"
