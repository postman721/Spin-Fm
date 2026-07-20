SHELL := /bin/sh
PYTHON ?= python3
DPKG_BUILDPACKAGE ?= dpkg-buildpackage
DPKG_CHECKBUILDDEPS ?= dpkg-checkbuilddeps

export PYTHONDONTWRITEBYTECODE := 1
export PYTEST_DISABLE_PLUGIN_AUTOLOAD := 1
export QT_QPA_PLATFORM := offscreen

.NOTPARALLEL:
.DEFAULT_GOAL := all
.PHONY: all permissions check tests deb

all:
	@$(MAKE) --no-print-directory check
#	@$(MAKE) --no-print-directory tests
	@$(MAKE) --no-print-directory deb

# GitHub artifact ZIPs normalize regular files to 0644. Invoke the repair tool
# through Python so this target works even when the tool's own execute bit was
# stripped during upload/download.
permissions:
	@$(PYTHON) -B tools/normalize_permissions.py --fix

# Check the native Debian toolchain and every declared Build-Depends.
check: permissions
	@command -v $(PYTHON) >/dev/null
	@command -v $(DPKG_BUILDPACKAGE) >/dev/null
	@command -v $(DPKG_CHECKBUILDDEPS) >/dev/null
	@command -v dpkg-deb >/dev/null
	@$(DPKG_CHECKBUILDDEPS)
	@$(PYTHON) -B -c "import magic, pytest, pyudev; from PyQt6 import QtCore, QtDBus, QtMultimedia, QtWidgets"
	@echo "Spin FM dependencies are available."

# Run runtime tests plus syntax, shell, cache, and legacy-file release gates.
tests: permissions
	@$(PYTHON) -B tools/source_archive.py --clean-only
	@PYTHONPATH="src$${PYTHONPATH:+:$$PYTHONPATH}" $(PYTHON) -B -m pytest -p no:cacheprovider --assert=plain
	@$(PYTHON) -B tools/check_syntax.py
	@sh -n bin/spin-fm debian/tests/smoke
	@$(PYTHON) -B tools/source_archive.py --check-clean
	@$(PYTHON) -B tools/source_archive.py --check-release

# Build only the unsigned Debian binary package and verify its contents.
deb: permissions
	@$(PYTHON) -B tools/source_archive.py --clean-only
	@$(PYTHON) -B tools/source_archive.py --check-release
	@$(DPKG_BUILDPACKAGE) -us -uc -b
	@set -eu; found=0; \
	for package in ../spin-fm_*.deb ../spin-fm-dbgsym_*.deb; do \
		[ -f "$$package" ] || continue; found=1; \
		if dpkg-deb --contents "$$package" | grep -E '(__pycache__/|\.py[co]$$|\$$py\.class$$|\.egg-info/|\.dist-info/)'; then \
			echo "Forbidden generated Python artifact in $$package" >&2; exit 1; \
		fi; \
	done; \
	[ "$$found" -eq 1 ] || { echo "No Debian package was produced." >&2; exit 1; }
