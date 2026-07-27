SHELL := /bin/sh
PYTHON ?= python3
DPKG_BUILDPACKAGE ?= dpkg-buildpackage
DPKG_CHECKBUILDDEPS ?= dpkg-checkbuilddeps

export PYTHONDONTWRITEBYTECODE := 1

.NOTPARALLEL:
.DEFAULT_GOAL := all
.PHONY: all permissions check verify deb

all:
	@$(MAKE) --no-print-directory check
	@$(MAKE) --no-print-directory verify
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
	@echo "Spin FM build dependencies are available."

# Run cache-free source, syntax, shell, and release-hygiene checks. Runtime test
# suites are intentionally excluded from this release while bulk-operation and
# memory work is being concentrated in the application itself.
verify: permissions
	@$(PYTHON) -B tools/source_archive.py --clean-only
	@$(PYTHON) -B tools/check_syntax.py
	@sh -n bin/spin-fm
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
