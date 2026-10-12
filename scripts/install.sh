#!/usr/bin/env bash
# Install logilens without Homebrew (macOS / Linux).
#
#   bash scripts/install.sh                     install or update
#   bash scripts/install.sh --download-jar      also download Logisim 2.7.1 (sha256-checked) if no jar is found
#   bash scripts/install.sh --uninstall         remove the virtualenv, data dir and the command link
#   bash scripts/install.sh --uninstall --purge also delete the build cache (compiled helper, Espresso)
#
# Options:
#   --python PATH   Python >= 3.11 to use (default: first of python3.14 … python3.11, python3)
#   --prefix DIR    data directory (default: ${XDG_DATA_HOME:-~/.local/share}/logilens)
#   --bin-dir DIR   where the command link goes (default: ~/.local/bin)
#   --recreate      delete and recreate the virtualenv
#   --force         replace an existing non-link file at <bin-dir>/logilens
#
# Layout: <prefix>/venv (virtualenv with the project; the package carries the Espresso sources),
# <bin-dir>/logilens -> <prefix>/venv/bin/logilens. Builds go to the user cache
# (macOS ~/Library/Caches/logilens, Linux ~/.cache/logilens). Re-running the script is safe.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP="logilens"
PREFIX="${XDG_DATA_HOME:-$HOME/.local/share}/$APP"
BIN_DIR="$HOME/.local/bin"
PYTHON=""
ACTION="install"
PURGE=0
RECREATE=0
FORCE=0
DOWNLOAD_JAR=0

JAR_URL="https://downloads.sourceforge.net/project/circuit/2.7.x/2.7.1/logisim-generic-2.7.1.jar"
JAR_SHA256="362a78c12ad18c203fed868872c4a01cd9c12141379d92e892bbe2c37e627bc2"

usage() { awk 'NR > 1 && !/^#/ { exit } NR > 1 { sub(/^# ?/, ""); print }' "${BASH_SOURCE[0]}"; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --uninstall) ACTION="uninstall" ;;
    --purge) PURGE=1 ;;
    --python) PYTHON="${2:?--python needs a path}"; shift ;;
    --prefix) PREFIX="${2:?--prefix needs a directory}"; shift ;;
    --bin-dir) BIN_DIR="${2:?--bin-dir needs a directory}"; shift ;;
    --recreate) RECREATE=1 ;;
    --force) FORCE=1 ;;
    --download-jar) DOWNLOAD_JAR=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "install.sh: unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

VENV="$PREFIX/venv"
LINK="$BIN_DIR/$APP"

if [[ -t 1 ]]; then B=$'\033[1m'; G=$'\033[32m'; Y=$'\033[33m'; R=$'\033[31m'; N=$'\033[0m'; else B=""; G=""; Y=""; R=""; N=""; fi
step() { printf '%s==>%s %s\n' "$B" "$N" "$*"; }
ok()   { printf '  %s✓%s %s\n' "$G" "$N" "$*"; }
warn() { printf '  %s!%s %s\n' "$Y" "$N" "$*"; }
die()  { printf '%sinstall.sh: %s%s\n' "$R" "$*" "$N" >&2; exit 1; }

sha256_of() {
  if command -v shasum >/dev/null 2>&1; then shasum -a 256 "$1" | awk '{print $1}'
  else sha256sum "$1" | awk '{print $1}'; fi
}

# ---------------------------------------------------------------------------------------------------- uninstall
if [[ "$ACTION" == "uninstall" ]]; then
  step "Uninstalling $APP"
  if [[ $PURGE -eq 1 && -x "$VENV/bin/$APP" ]]; then
    "$VENV/bin/$APP" --lang en cache clear --all >/dev/null 2>&1 && ok "build cache cleared" || warn "could not clear the cache"
    CACHE="$("$VENV/bin/python" -c 'from logilens.env.paths import cache_dir; print(cache_dir())' 2>/dev/null || true)"
    if [[ -n "$CACHE" && -d "$CACHE" && "$(basename "$CACHE")" == "$APP" ]]; then
      rm -rf -- "$CACHE" && ok "removed $CACHE"
    fi
  fi
  if [[ -L "$LINK" ]]; then
    target="$(readlink "$LINK")"
    if [[ "$target" == "$VENV/bin/$APP" ]]; then rm -f -- "$LINK" && ok "removed link $LINK"
    else warn "$LINK points to $target (not this installation) — left alone"; fi
  elif [[ -e "$LINK" ]]; then
    warn "$LINK is not a link created by this script — left alone"
  fi
  if [[ -d "$PREFIX" ]]; then
    [[ "$(basename "$PREFIX")" == "$APP" || -d "$PREFIX/venv" ]] || die "refusing to delete unexpected directory $PREFIX"
    rm -rf -- "$PREFIX" && ok "removed $PREFIX"
  else
    ok "nothing installed in $PREFIX"
  fi
  [[ $PURGE -eq 1 ]] || echo "  (the build cache is kept; add --purge to delete it)"
  exit 0
fi

# ---------------------------------------------------------------------------------------------------- install
[[ -f "$ROOT/pyproject.toml" && -d "$ROOT/src/logilens" ]] || die "run this script from a logilens checkout"

py_ok() { "$1" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' >/dev/null 2>&1; }

step "Looking for Python >= 3.11"
if [[ -n "$PYTHON" ]]; then
  py_ok "$PYTHON" || die "$PYTHON is not a working Python >= 3.11"
else
  for cand in python3.14 python3.13 python3.12 python3.11 python3; do
    if command -v "$cand" >/dev/null 2>&1 && py_ok "$(command -v "$cand")"; then PYTHON="$(command -v "$cand")"; break; fi
  done
  [[ -n "$PYTHON" ]] || die "Python >= 3.11 not found (macOS: brew install python; Debian/Ubuntu: apt install python3 python3-venv)"
fi
ok "$PYTHON ($("$PYTHON" -c 'import platform; print(platform.python_version())'))"

step "Virtualenv $VENV"
if [[ $RECREATE -eq 1 && -d "$VENV" ]]; then rm -rf -- "$VENV"; ok "removed old virtualenv"; fi
if [[ -x "$VENV/bin/python" ]] && "$VENV/bin/python" -c 'import sys' >/dev/null 2>&1; then
  ok "reusing the existing virtualenv"
else
  rm -rf -- "$VENV"
  mkdir -p "$PREFIX"
  "$PYTHON" -m venv "$VENV" || die "python -m venv failed (Debian/Ubuntu: apt install python3-venv)"
  ok "created"
fi

step "Installing $APP and its dependencies (pip)"
"$VENV/bin/python" -m pip install --quiet --disable-pip-version-check --upgrade pip >/dev/null 2>&1 || true
"$VENV/bin/python" -m pip install --quiet --disable-pip-version-check --upgrade "$ROOT" \
  || die "pip install failed (see the messages above)"
# a same-version reinstall must still pick up changed sources
"$VENV/bin/python" -m pip install --quiet --disable-pip-version-check --force-reinstall --no-deps "$ROOT" \
  || die "pip install failed (see the messages above)"
ok "$("$VENV/bin/$APP" --version)"

if [[ $DOWNLOAD_JAR -eq 1 ]]; then
  step "Logisim 2.7.1 jar"
  FOUND="$("$VENV/bin/python" -c 'from logilens.backends.java.locate import find_jar; print(find_jar() or "")')"
  if [[ -n "$FOUND" ]]; then
    ok "already available: $FOUND"
  else
    CACHE="$("$VENV/bin/python" -c 'from logilens.env.paths import cache_dir; print(cache_dir())')"
    mkdir -p "$CACHE"
    TMP="$(mktemp "$CACHE/.logisim.jar.XXXXXX")"
    if curl -fsSL --retry 2 -o "$TMP" "$JAR_URL" && [[ "$(sha256_of "$TMP")" == "$JAR_SHA256" ]]; then
      mv -f -- "$TMP" "$CACHE/logisim.jar"
      ok "downloaded and verified: $CACHE/logisim.jar"
    else
      rm -f -- "$TMP"
      warn "download failed or sha256 mismatch — the Python backend will be used (or pass --logisim-jar)"
    fi
  fi
fi

step "Building Espresso and the Java helper (logilens setup)"
if "$VENV/bin/$APP" --lang en --no-color setup; then
  ok "setup finished"
else
  warn "setup reported a problem (Espresso needs make + a C compiler; the helper needs a JDK and logisim.jar)"
fi

step "Command link $LINK"
mkdir -p "$BIN_DIR"
if [[ -e "$LINK" && ! -L "$LINK" && $FORCE -eq 0 ]]; then
  die "$LINK exists and is not a link; move it away or re-run with --force"
fi
ln -sfn "$VENV/bin/$APP" "$LINK"
ok "$LINK -> $VENV/bin/$APP"

step "Environment check (logilens doctor)"
"$VENV/bin/$APP" --lang en --no-color doctor || warn "doctor reported problems (see the table above)"

case ":$PATH:" in
  *":$BIN_DIR:"*) echo; ok "done — run: $APP --help" ;;
  *)
    echo
    warn "$BIN_DIR is not on your PATH. Add it, e.g.:"
    case "${SHELL##*/}" in
      zsh)  echo "      echo 'export PATH=\"$BIN_DIR:\$PATH\"' >> ~/.zshrc && exec zsh" ;;
      bash) echo "      echo 'export PATH=\"$BIN_DIR:\$PATH\"' >> ~/.bashrc && exec bash" ;;
      fish) echo "      fish_add_path $BIN_DIR" ;;
      *)    echo "      export PATH=\"$BIN_DIR:\$PATH\"" ;;
    esac
    echo "    or run it directly: $LINK --help"
    ;;
esac
