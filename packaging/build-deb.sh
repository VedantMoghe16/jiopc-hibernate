#!/usr/bin/env bash
# build-deb.sh — build jiopc-hibernate_<version>_all.deb with plain dpkg-deb.
#
# The package is pure-Python, stdlib-only, architecture "all". It installs:
#
#   /opt/jiopc-hibernate/lib/jiopc_hibernate/...   the Python package
#   /usr/bin/jiopc-hibernate{,-guard,-restore,-save,-leave}   launchers
#   /usr/bin/lxqt-leave                                      diverted wrapper
#   /etc/xdg/autostart/jiopc-hibernate-guard.desktop          Component A (idle)
#   /etc/xdg/autostart/jiopc-hibernate-restore.desktop        Component E (login)
#   /etc/jiopc-hibernate/{config.json,handlers.json}          editable references
#   /usr/share/doc/jiopc-hibernate/{copyright,changelog.gz,...}
#
# It installs cleanly on a fresh Ubuntu 24.04 + LxQt VM with no user
# interaction: the autostart entries in /etc/xdg/autostart apply to every
# user's LxQt session automatically, and postinst binds lxqt-leave through
# jiopc-hibernate-leave so manual logout saves before windows are closed.
#
# Run on Ubuntu 24.04 (or any host with dpkg-deb). On macOS dev machines only
# `bash -n packaging/build-deb.sh` syntax-checking and a --dry-run stage are
# possible (dpkg-deb is absent); the script detects this and stops cleanly.
#
# Usage:
#   packaging/build-deb.sh            # build the .deb
#   packaging/build-deb.sh --stage    # stage the tree only (no dpkg-deb)

set -euo pipefail

PKG_NAME="jiopc-hibernate"
PKG_ARCH="all"
PKG_MAINTAINER="Team InnovAstra <developer@moxiebeauty.in>"
PKG_SECTION="utils"
PKG_PRIORITY="optional"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Single source of truth for the version: src/jiopc_hibernate/__init__.py
PKG_VERSION="$(sed -n 's/^__version__ = "\(.*\)"$/\1/p' \
    "${REPO_ROOT}/src/jiopc_hibernate/__init__.py")"
if [[ -z "${PKG_VERSION}" ]]; then
    echo "error: could not read __version__ from src/jiopc_hibernate/__init__.py" >&2
    exit 1
fi

OUT_DIR="${REPO_ROOT}/packaging/dist"
DEB_FILE="${OUT_DIR}/${PKG_NAME}_${PKG_VERSION}_${PKG_ARCH}.deb"
INSTALL_ROOT="/opt/jiopc-hibernate"

STAGE_ONLY=0
[[ "${1:-}" == "--stage" ]] && STAGE_ONLY=1

# --- staging tree ------------------------------------------------------------
BUILD="$(mktemp -d)"
trap 'rm -rf "${BUILD}"' EXIT
echo ">> staging into ${BUILD}"

# 1) Python package
install -d "${BUILD}${INSTALL_ROOT}/lib"
cp -r "${REPO_ROOT}/src/jiopc_hibernate" "${BUILD}${INSTALL_ROOT}/lib/"
find "${BUILD}${INSTALL_ROOT}/lib" -name '__pycache__' -type d -prune -exec rm -rf {} +

# 2) launchers → /usr/bin
install -d "${BUILD}/usr/bin"
for f in jiopc-hibernate jiopc-hibernate-guard jiopc-hibernate-restore jiopc-hibernate-save; do
    install -m 0755 "${REPO_ROOT}/integration/bin/${f}" "${BUILD}/usr/bin/${f}"
done
install -m 0755 "${REPO_ROOT}/integration/lxqt/jiopc-hibernate-leave" "${BUILD}/usr/bin/jiopc-hibernate-leave"

# 3) XDG autostart (system-wide; applies to every LxQt session)
install -d "${BUILD}/etc/xdg/autostart"
install -m 0644 "${REPO_ROOT}/integration/autostart/jiopc-hibernate-guard.desktop" \
    "${BUILD}/etc/xdg/autostart/"
install -m 0644 "${REPO_ROOT}/integration/autostart/jiopc-hibernate-restore.desktop" \
    "${BUILD}/etc/xdg/autostart/"

# 4) editable reference config + the master handler list
install -d "${BUILD}/etc/jiopc-hibernate"
install -m 0644 "${REPO_ROOT}/config/config.json"   "${BUILD}/etc/jiopc-hibernate/config.json"
install -m 0644 "${REPO_ROOT}/config/handlers.json" "${BUILD}/etc/jiopc-hibernate/handlers.json"

# 5) docs
DOCDIR="${BUILD}/usr/share/doc/${PKG_NAME}"
install -d "${DOCDIR}"
for d in README.md DESIGN.md SCHEMA.md; do
    [[ -f "${REPO_ROOT}/${d}" ]] && install -m 0644 "${REPO_ROOT}/${d}" "${DOCDIR}/"
done
cat > "${DOCDIR}/copyright" <<EOF
Files: *
Copyright: 2026 Team InnovAstra
License: Proprietary — JioPC x IIT Bombay Hackathon 2026 submission.
EOF
printf '%s (%s) noble; urgency=low\n\n  * See CHANGELOG.md / DESIGN.md.\n\n -- %s  %s\n' \
    "${PKG_NAME}" "${PKG_VERSION}" "${PKG_MAINTAINER}" "$(date -R 2>/dev/null || date)" \
    | gzip -9 > "${DOCDIR}/changelog.gz"

# --- DEBIAN control ----------------------------------------------------------
install -d "${BUILD}/DEBIAN"
INSTALLED_KB="$(du -sk "${BUILD}" | cut -f1)"
cat > "${BUILD}/DEBIAN/control" <<EOF
Package: ${PKG_NAME}
Version: ${PKG_VERSION}
Architecture: ${PKG_ARCH}
Maintainer: ${PKG_MAINTAINER}
Installed-Size: ${INSTALLED_KB}
Section: ${PKG_SECTION}
Priority: ${PKG_PRIORITY}
Depends: python3 (>= 3.10)
Recommends: wmctrl, libnotify-bin
Suggests: xdotool, xprintidle, zenity, x11-utils
Description: JioPC application-level cross-VM session save & restore
 Saves the running GUI session (open apps, geometry, per-app in-app state)
 to the persistent home directory on disconnect, and offers to restore it on
 the next login on any VM in the pool. User-space, no root, stdlib-only.
 Integrates with the LxQt session via XDG autostart and a dpkg-diverted
 lxqt-leave wrapper, so logout saves before windows are closed while normal
 logout continues. Never crashes the desktop session.
EOF

cp "${REPO_ROOT}/packaging/debian/postinst" "${BUILD}/DEBIAN/postinst"
cp "${REPO_ROOT}/packaging/debian/prerm"    "${BUILD}/DEBIAN/prerm"
cp "${REPO_ROOT}/packaging/debian/conffiles" "${BUILD}/DEBIAN/conffiles"
chmod 0755 "${BUILD}/DEBIAN/postinst" "${BUILD}/DEBIAN/prerm"

# --- syntax-check the maintainer scripts ------------------------------------
bash -n "${BUILD}/DEBIAN/postinst"
bash -n "${BUILD}/DEBIAN/prerm"

if [[ "${STAGE_ONLY}" -eq 1 ]]; then
    echo ">> staged tree (control + scripts validated); --stage stops here."
    find "${BUILD}" -maxdepth 3 -not -path '*/__pycache__*' | sed "s#${BUILD}#  #"
    exit 0
fi

if ! command -v dpkg-deb >/dev/null 2>&1; then
    echo "error: dpkg-deb not found — run on Ubuntu, or use --stage on macOS." >&2
    exit 3
fi

# --- build -------------------------------------------------------------------
mkdir -p "${OUT_DIR}"
dpkg-deb --root-owner-group --build "${BUILD}" "${DEB_FILE}"
echo ">> built ${DEB_FILE}"
dpkg-deb --info "${DEB_FILE}"
echo ">> contents:"
dpkg-deb --contents "${DEB_FILE}"
