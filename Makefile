SHELL := /bin/sh

ARCHIVE ?= spin-fm.tar.gz
SOURCE_DIR ?= $(strip $(shell tar -tzf "$(ARCHIVE)" 2>/dev/null | awk -F/ 'NF { print $$1; exit }'))
EXTRACT_STAMP := .spin-fm-source-extracted

.NOTPARALLEL:
.DEFAULT_GOAL := all
.PHONY: all prepare permissions check tests deb clean help

all: prepare
	@$(MAKE) -C "$(SOURCE_DIR)" --no-print-directory all

prepare: $(EXTRACT_STAMP)

$(EXTRACT_STAMP): $(ARCHIVE)
	@set -eu; \
	archive="$(ARCHIVE)"; source_dir="$(SOURCE_DIR)"; \
	[ -n "$$source_dir" ] || { echo "Unable to determine the source directory in $$archive." >&2; exit 1; }; \
	[ -f "$$archive" ] || { echo "Missing source archive: $$archive" >&2; exit 1; }; \
	if tar -tzf "$$archive" | awk '/^\// || /(^|\/)\.\.($$|\/)/ { bad=1 } END { exit bad ? 0 : 1 }'; then \
		echo "Unsafe path found in $$archive." >&2; exit 1; \
	fi; \
	roots=$$(tar -tzf "$$archive" | awk -F/ 'NF && $$1 != "" { print $$1 }' | sort -u); \
	[ "$$(printf '%s\n' "$$roots" | sed '/^$$/d' | wc -l)" -eq 1 ] || { \
		echo "$$archive must contain exactly one top-level source directory." >&2; exit 1; \
	}; \
	[ "$$roots" = "$$source_dir" ] || { \
		echo "Archive root '$$roots' does not match SOURCE_DIR '$$source_dir'." >&2; exit 1; \
	}; \
	rm -rf -- "$$source_dir"; \
	tar -xzf "$$archive"; \
	[ -f "$$source_dir/Makefile" ] || { echo "No Makefile found in extracted source." >&2; exit 1; }; \
	touch "$@"

permissions check tests deb: prepare
	@$(MAKE) -C "$(SOURCE_DIR)" --no-print-directory $@

clean:
	@set -eu; \
	[ -z "$(SOURCE_DIR)" ] || rm -rf -- "$(SOURCE_DIR)"; \
	rm -f "$(EXTRACT_STAMP)"

help:
	@printf '%s\n' \
		'make all          Extract, validate, test, and build the Debian package' \
		'make check        Extract and verify build dependencies' \
		'make tests        Extract and run the project test suite' \
		'make deb          Extract and build the Debian package' \
		'make permissions  Restore required executable permissions' \
		'make clean        Remove the extracted source tree'
