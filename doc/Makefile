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

# The part on the methods behind the defaults: plain LaTeX chapters, the
# tables generated for them, and the bibliography they cite.
METHODS_TEX=	$(wildcard methods/*.tex methods/tables/*.tex)

.PHONY: all check clean distclean

all: ${DOC}

# `make check` builds the PDF and checks the build (check.mk); what it
# accepts: src/scholar/cli.nw, sec:woven-document.
CHECK_JOB=	scholar
CHECK_SOURCES=	scholar.tex preamble.tex ${SRC_TEX} ${METHODS_TEX} bibliography.bib

scholar.pdf: scholar.tex preamble.tex
scholar.pdf: ${SRC_TEX}
scholar.pdf: ${METHODS_TEX} bibliography.bib
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
include check.mk

# The document uses biblatex with biber.  When the .bbl is missing,
# latexmk (run with -use-make) asks make for it, and the shared tex.mk
# offers two pattern rules: the first, from the .aux, runs bibtexu, which
# finds no \bibdata in a biblatex .aux and fails (#311).  This explicit
# rule wins over both and runs biber on the .bcf.
${TEX_OUTDIR}/scholar.bbl: ${TEX_OUTDIR}/scholar.bcf
	${BIBLIOGRAPHY.bcf}

clean:
	${RM} ${DOC}
	${RM} noweb_lexer.py
	${MAKE} -C ../src/scholar clean

distclean:
