# Builds the librarian handout. Run inside this directory's Flox environment:
#
#   flox activate -- make          # build/librarian-handout.pdf and .html
#   flox activate -- make serve    # live preview at http://localhost:8080
#   flox activate -- make check    # fails if a page's content runs off the page
#
# marp-cli, gnumake, and a browser are pinned in .flox/env/manifest.toml, and the activation
# hook points CHROME_PATH at the browser (resolve-chrome.sh). The handout's palette is the
# assistant's own, library_assistant/static/palette.css, so a change there rebuilds it too.

MARP    := marp
DOC     := librarian-handout.md
BUILD   := build
PALETTE := ../../library_assistant/static/palette.css

# The activation hook sets this; resolving it here too covers a shell where it didn't run.
# HTML export does not need a browser, so a miss here is not fatal.
_resolved_chrome := $(shell ./resolve-chrome.sh 2>/dev/null)
ifneq ($(_resolved_chrome),)
  export CHROME_PATH := $(_resolved_chrome)
endif

.PHONY: all html pdf watch serve check check-marp clean

all: check-marp html pdf

html: check-marp $(BUILD)/librarian-handout.html
pdf: check-marp $(BUILD)/librarian-handout.pdf

DEPS := $(DOC) handout.css $(PALETTE) .marprc.yml

check-marp:
	@command -v $(MARP) >/dev/null 2>&1 || { \
	  printf '%s\n' \
	    '' \
	    '  marp is not on PATH. The handout'"'"'s toolchain is this directory'"'"'s Flox' \
	    '  environment; run from docs/handout:' \
	    '' \
	    '    flox activate -- make' \
	    '' >&2; \
	  exit 1; \
	}

$(BUILD)/librarian-handout.html: $(DEPS)
	$(MARP) --config-file .marprc.yml $(DOC) -o $@

$(BUILD)/librarian-handout.pdf: $(DEPS)
	$(MARP) --config-file .marprc.yml $(DOC) --pdf -o $@

# Live preview at http://localhost:8080 with reload on save.
#
# Do not pass `.` to --watch. After `flox activate`, `.flox/run` is a symlink into the Nix
# store; Marp's chokidar follows it and dies with EMFILE on macOS. Serve a directory of
# links to just the sources instead.
SERVE_ROOT := .serve

serve: check-marp
	@mkdir -p $(SERVE_ROOT)
	@ln -sfn ../$(DOC) $(SERVE_ROOT)/$(DOC)
	$(MARP) --config-file .marprc.yml --server --watch $(SERVE_ROOT)

watch: check-marp
	$(MARP) --config-file .marprc.yml $(DOC) --watch -o $(BUILD)/librarian-handout.html

# Fails if any page's content runs past the bottom of the page: the bug you can't see in
# the editor and can't miss on paper.
check: check-marp
	@./check-overflow.sh $(DOC)

clean:
	rm -rf $(BUILD) $(SERVE_ROOT)
