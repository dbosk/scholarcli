# check.mk: build a LaTeX document and check that it built (#279).
#
# Include after the shared tex.mk (or noweb.mk), with CHECK_JOB set to the
# document's job name and CHECK_SOURCES to the files it is built from.
# `make check` builds ${CHECK_JOB}.pdf and fails unless the log and the PDF
# exist, the log is newer than every source, and check-settled.py (beside
# this file) accepts the log: no error, no undefined reference, and
# references that settled or alternate between two states (a two-state
# flip, which passes with a named warning; see check-settled.py).
#
# A LaTeX error does not reliably fail the shared build rule: it ignores
# the exit status of its first latexmk run (even 127, no latexmk at all)
# and its rerun loop ends in a successful `break`.  That is why the PDF
# is built by a sub-make whose status is ignored and the outputs are
# checked afterwards.  Run it non-interactively, e.g.
#   make check LATEXFLAGS="-shell-escape -interaction=nonstopmode"
# The extra runs pass LATEXFLAGS to pdflatex as latexmk does.

CHECK_DIR:=	$(dir $(lastword $(MAKEFILE_LIST)))
CHECK_JOB?=	scholar
CHECK_SOURCES?=	${CHECK_JOB}.tex
CHECK_LOG=	${TEX_OUTDIR}/${CHECK_JOB}.log
CHECK_ENGINE=	pdflatex -8bit ${LATEXFLAGS} -recorder \
		-output-directory=${TEX_OUTDIR} ${CHECK_JOB}.tex

# latexmk stops after 5 pdflatex runs by default.  From a clean ltxobj/
# the scholar document needed 7 before its .aux stopped changing (the
# didactic package's page records settle last), so latexmk gave up with
# "Maximum runs" (#279).  10 leaves room.  The shared tex.mk sets
# PDFLATEX with ?=, so this wins and LATEXFLAGS still applies.
PDFLATEX=	latexmk -pdf -use-make -8bit -e '$$max_repeat=10'

.PHONY: check
check:
	-@${MAKE} ${CHECK_JOB}.pdf
	@for f in ${CHECK_LOG} ${TEX_OUTDIR}/${CHECK_JOB}.pdf; do \
	  [ -e $$f ] || { echo "check: $$f is missing; the build did not run" >&2; \
	                  exit 1; }; \
	done
	@for f in ${CHECK_SOURCES}; do \
	  [ ${CHECK_LOG} -nt $$f ] || { \
	    echo "check: ${CHECK_LOG} is older than $$f; the build did not run" >&2; \
	    exit 1; }; \
	done
	@python3 ${CHECK_DIR}check-settled.py ${CHECK_JOB} ${TEX_OUTDIR} \
	  ${CHECK_ENGINE}
	@ln -sf ${TEX_OUTDIR}/${CHECK_JOB}.pdf ${CHECK_JOB}.pdf
