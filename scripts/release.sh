#!/usr/bin/env bash
# Build the sdist + wheel of logilens into dist/ and print the sha256 needed by the Homebrew formula.
#
#   scripts/release.sh                 release build: refuses a .dev version, runs the fast tests first
#   scripts/release.sh --build-only    just build (any version, no tests) — used by `make build`
#   scripts/release.sh --skip-tests    release build without running the tests
#   scripts/release.sh --out DIR       write the artifacts to DIR instead of dist/
#
# Builder: `python -m build` when the `build` package is importable, otherwise `uv build`, otherwise `hatch build`.
# Set GITHUB_USER to get ready-to-paste URLs (default: xoliinykb-stack).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="${PYTHON:-$ROOT/.venv/bin/python}"
[[ -x "$PY" ]] || PY="$(command -v python3)"
OUT="$ROOT/dist"
BUILD_ONLY=0
SKIP_TESTS=0
OWNER="${GITHUB_USER:-xoliinykb-stack}"

usage() { awk 'NR > 1 && !/^#/ { exit } NR > 1 { sub(/^# ?/, ""); print }' "${BASH_SOURCE[0]}"; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --build-only) BUILD_ONLY=1 ;;
    --skip-tests) SKIP_TESTS=1 ;;
    --out) OUT="$(mkdir -p "$2" && cd "$2" && pwd)"; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "release.sh: unknown option $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

say() { printf '\033[1m==>\033[0m %s\n' "$*"; }
die() { printf 'release.sh: %s\n' "$*" >&2; exit 1; }

sha256() {
  if command -v shasum >/dev/null 2>&1; then shasum -a 256 "$1" | awk '{print $1}'
  else sha256sum "$1" | awk '{print $1}'; fi
}

VERSION="$(sed -n 's/^__version__ = "\(.*\)"$/\1/p' "$ROOT/src/logilens/__init__.py")"
[[ -n "$VERSION" ]] || die "cannot read __version__ from src/logilens/__init__.py"
say "logilens $VERSION"

if [[ $BUILD_ONLY -eq 0 ]]; then
  if [[ "$VERSION" =~ (dev|a[0-9]|b[0-9]|rc) ]]; then
    die "version $VERSION is a pre-release; bump __version__ first, or use --build-only"
  fi
  if [[ $SKIP_TESTS -eq 0 ]]; then
    say "running the fast test suite (-m 'not java')"
    (cd "$ROOT" && "$PY" -m pytest tests -q -m "not java")
  fi
fi

rm -rf "$OUT"
mkdir -p "$OUT"
cd "$ROOT"
if "$PY" -I -c "import build.__main__" >/dev/null 2>&1; then
  say "building with python -m build"
  "$PY" -I -m build --sdist --wheel --outdir "$OUT" "$ROOT"
elif command -v uv >/dev/null 2>&1; then
  say "building with uv build"
  uv build --sdist --wheel --out-dir "$OUT" "$ROOT"
elif command -v hatch >/dev/null 2>&1; then
  say "building with hatch build"
  hatch build -t sdist -t wheel "$OUT"
else
  die "no builder found: install one of  '$PY -m pip install build',  uv,  hatch"
fi

SDIST="$(ls "$OUT"/logilens-"$VERSION".tar.gz 2>/dev/null || true)"
[[ -f "$SDIST" ]] || die "sdist not found in $OUT"

# Sanity: the sdist must carry what the Homebrew formula builds from.
for needed in third_party/espresso/espresso-src/Makefile java/LogisimBridge.java \
              examples/converter_draft.circ examples/converter_nand_nor.circ examples/converter.spec.txt \
              examples/moore_fsm.circ; do
  tar -tzf "$SDIST" | grep -q "/$needed\$" || die "sdist is missing $needed"
done
if tar -tzf "$SDIST" | grep -qi 'logisim[^/]*\.jar$'; then
  die "sdist contains a Logisim jar — it must never be bundled (GPL)"
fi

SUM="$(sha256 "$SDIST")"
echo
say "artifacts in $OUT"
for f in "$OUT"/*; do printf '  %s  %s\n' "$(sha256 "$f")" "$(basename "$f")"; done
echo
say "Homebrew formula stanza (packaging/homebrew/logilens.rb):"
cat <<EOF
  url "https://github.com/$OWNER/logilens/releases/download/v$VERSION/$(basename "$SDIST")"
  sha256 "$SUM"
EOF
if [[ $BUILD_ONLY -eq 0 ]]; then
  echo
  say "next steps"
  cat <<EOF
  git tag -a v$VERSION -m "logilens $VERSION" && git push origin v$VERSION
  gh release create v$VERSION "$SDIST" "$OUT"/*.whl --title "logilens $VERSION" --generate-notes
  # then update url + sha256 in Formula/logilens.rb of $OWNER/homebrew-tap (see the comment at the top of packaging/homebrew/logilens.rb)
EOF
fi
