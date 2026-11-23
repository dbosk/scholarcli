DOC+=		scholar.pdf

SRC_TEX+=	../src/scholar/scholar.tex
SRC_TEX+=	../src/scholar/utils.tex
SRC_TEX+=	../src/scholar/cache.tex
SRC_TEX+=	../src/scholar/ratelimit.tex
SRC_TEX+=	../src/scholar/network.tex
SRC_TEX+=	../src/scholar/providers.tex
SRC_TEX+=	../src/scholar/enrich.tex
SRC_TEX+=	../src/scholar/crossref.tex
SRC_TEX+=	../src/scholar/unpaywall.tex
SRC_TEX+=	../src/scholar/europepmc.tex
SRC_TEX+=	../src/scholar/preprint.tex
SRC_TEX+=	../src/scholar/pdf.tex
SRC_TEX+=	../src/scholar/notes.tex
SRC_TEX+=	../src/scholar/review.tex
SRC_TEX+=	../src/scholar/llm_review.tex
SRC_TEX+=	../src/scholar/agreement.tex
SRC_TEX+=	../src/scholar/cli.tex
SRC_TEX+=	../src/scholar/tui.tex
SRC_TEX+=	../src/scholar/tutorials/first-search.tex
SRC_TEX+=	../src/scholar/tutorials/reviewing-in-the-tui.tex
SRC_TEX+=	../src/scholar/tutorials/enrich-verify-export.tex
SRC_TEX+=	../src/scholar/tutorials/llm-synthesis.tex
SRC_TEX+=	../src/scholar/tutorials/scholar-with-an-agent.tex

.PHONY: all check clean distclean

all: ${DOC}

# A LaTeX error does not reliably fail the build: the shared rule ignores
# the exit status of its first latexmk run (even 127, no latexmk at all)
# and its rerun loop ends in a successful `break`.  This target fails
# unless the PDF and the log exist and the log is newer than every
# source, and when that log holds an error, an undefined reference or
# cross-references that did not settle (#279).  latexmk's own "Maximum
# runs of pdflatex reached" goes to the terminal, not to the log; the
# log lines it reacts to are what we find.  Run it non-interactively:
#   make check LATEXFLAGS="-shell-escape -interaction=nonstopmode"
CHECK_LOG=	${TEX_OUTDIR}/scholar.log
CHECK_PATTERNS=	-e '^! ' -e 'There were undefined' \
		-e 'Label(s) may have changed' -e 'Rerun to get'

check: scholar.pdf
	@for f in ${CHECK_LOG} ${TEX_OUTDIR}/scholar.pdf scholar.pdf; do \
	  [ -e $$f ] || { echo "check: $$f is missing; the build did not run" >&2; \
	                  exit 1; }; \
	done
	@for f in scholar.tex preamble.tex ${SRC_TEX}; do \
	  [ ${CHECK_LOG} -nt $$f ] || { \
	    echo "check: ${CHECK_LOG} is older than $$f; the build did not run" >&2; \
	    exit 1; }; \
	done
	@! grep -n -A3 ${CHECK_PATTERNS} ${CHECK_LOG}

scholar.pdf: scholar.tex preamble.tex
scholar.pdf: ${SRC_TEX}
# The woven .tex ask minted to load noweb's custom lexer; noweb.mk provides the
# rule that copies it here from noweb's library directory.
scholar.pdf: noweb_lexer.py

# The tutorials live one directory further down; this rule must exist
# because the generic ../src/scholar/%.tex rule also matches their path
# (with stem tutorials/<id>) and would run make in the wrong directory.
# GNU make prefers the rule with the shorter stem, so this one wins.
# Each rule names the .nw behind the .tex: without it, make found an
# existing woven .tex up to date and built the PDF from a stale chapter
# (#279).
../src/scholar/tutorials/%.tex: ../src/scholar/tutorials/%.nw
	${MAKE} -C ../src/scholar/tutorials $(notdir $@)

# Build .tex files in src/scholar if they don't exist or are outdated
../src/scholar/%.tex: ../src/scholar/%.nw
	${MAKE} -C ../src/scholar $(notdir $@)

INCLUDE_MAKEFILES=../makefiles
include ${INCLUDE_MAKEFILES}/noweb.mk

clean:
	${RM} ${DOC}
	${RM} noweb_lexer.py
	${MAKE} -C ../src/scholar clean

distclean:
