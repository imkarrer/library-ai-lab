# Builds the librarian handout, the demo deck, and the two sheets for district IT (the
# network request and the HTTPS rollout, in ../templates). Run inside this directory's Flox
# environment:
#
#   flox activate -- make          # every document into build/, as .pdf and .html
#   flox activate -- make serve    # live preview at http://localhost:8080
#   flox activate -- make check    # fails if a page or slide's content runs off it
#
# marp-cli, gnumake, and a browser are pinned in .flox/env/manifest.toml, and the activation
# hook points CHROME_PATH at the browser (resolve-chrome.sh). The handout's palette is the
# assistant's own, library_assistant/static/palette.css, so a change there rebuilds it too.

# --no-stdin: with stdin not a terminal (an agent, CI), Marp waits to read Markdown from it.
MARP    := marp --no-stdin
DOC     := librarian-handout.md
DECK    := demo-deck.md
# The IT sheets live with the other school templates; they use the handout's look.
IT_DOCS := ../templates/it-network-request.md ../templates/it-https-rollout.md
IT_HTML  = $(patsubst ../templates/%.md,$(BUILD)/%.html,$(IT_DOCS))
IT_PDF   = $(patsubst ../templates/%.md,$(BUILD)/%.pdf,$(IT_DOCS))
BUILD   := build
PALETTE := ../../library_assistant/static/palette.css
COMPONENTS := ../../library_assistant/static/components.css

# The activation hook sets this; resolving it here too covers a shell where it didn't run.
# HTML export does not need a browser, so a miss here is not fatal.
_resolved_chrome := $(shell ./resolve-chrome.sh 2>/dev/null)
ifneq ($(_resolved_chrome),)
  export CHROME_PATH := $(_resolved_chrome)
endif

.PHONY: all html pdf watch serve check check-marp clean

all: check-marp html pdf

html: check-marp $(BUILD)/librarian-handout.html $(BUILD)/demo-deck.html $(IT_HTML)
pdf: check-marp $(BUILD)/librarian-handout.pdf $(BUILD)/demo-deck.pdf $(IT_PDF)

DEPS := $(DOC) handout.css $(PALETTE) $(COMPONENTS) .marprc.yml
DECK_DEPS := $(DECK) deck.css $(PALETTE) $(COMPONENTS) .marprc.yml

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

$(BUILD)/demo-deck.html: $(DECK_DEPS)
	$(MARP) --config-file .marprc.yml $(DECK) -o $@

$(BUILD)/demo-deck.pdf: $(DECK_DEPS)
	$(MARP) --config-file .marprc.yml $(DECK) --pdf -o $@

IT_DEPS := handout.css $(PALETTE) $(COMPONENTS) .marprc.yml

$(BUILD)/%.html: ../templates/%.md $(IT_DEPS)
	$(MARP) --config-file .marprc.yml $< -o $@

$(BUILD)/%.pdf: ../templates/%.md $(IT_DEPS)
	$(MARP) --config-file .marprc.yml $< --pdf -o $@

# Live preview at http://localhost:8080 with reload on save.
#
# Do not pass `.` to --watch. After `flox activate`, `.flox/run` is a symlink into the Nix
# store; Marp's chokidar follows it and dies with EMFILE on macOS. Serve a directory of
# links to just the sources instead.
SERVE_ROOT := .serve

serve: check-marp
	@mkdir -p $(SERVE_ROOT)
	@ln -sfn ../$(DOC) $(SERVE_ROOT)/$(DOC)
	@ln -sfn ../$(DECK) $(SERVE_ROOT)/$(DECK)
	@for doc in $(IT_DOCS); do ln -sfn ../$$doc $(SERVE_ROOT)/$$(basename $$doc); done
	$(MARP) --config-file .marprc.yml --server --watch $(SERVE_ROOT)

watch: check-marp
	$(MARP) --config-file .marprc.yml $(DOC) --watch -o $(BUILD)/librarian-handout.html

# Fails if any page's content runs past the bottom of the page: the bug you can't see in
# the editor and can't miss on paper.
check: check-marp
	@./check-overflow.sh $(DOC)
	@./check-overflow.sh $(DECK)
	@for doc in $(IT_DOCS); do ./check-overflow.sh $$doc || exit 1; done

clean:
	rm -rf $(BUILD) $(SERVE_ROOT)
