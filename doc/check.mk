# check.mk: `make check` builds ${CHECK_JOB}.pdf and checks what the
# build left with check-settled.py (beside this file), which passes a
# cycle of the references (a state that comes back within a few extra
# runs) with a warning and fails what does not settle.  Include it after
# the shared tex.mk (or noweb.mk), with CHECK_JOB set to the job name and
# CHECK_SOURCES to the files the document is built from.  What it accepts
# and why: src/scholar/cli.nw, section "Keeping the woven document
# buildable" (sec:woven-document).  Run it non-interactively, e.g.
#   make check LATEXFLAGS="-shell-escape -interaction=nonstopmode"

CHECK_DIR:=	$(dir $(lastword $(MAKEFILE_LIST)))
CHECK_JOB?=	scholar
CHECK_SOURCES?=	${CHECK_JOB}.tex
CHECK_ENGINE=	pdflatex -8bit ${LATEXFLAGS} -recorder \
		-output-directory=${TEX_OUTDIR} ${CHECK_JOB}.tex

# From a clean ltxobj/ the scholar document needed 7 runs before its .aux
# stopped changing, and latexmk stops at 5 by default; 10 leaves room.
# The shared tex.mk sets PDFLATEX with ?=, so this wins.
PDFLATEX=	latexmk -pdf -use-make -8bit -e '$$max_repeat=10'

.PHONY: check
check:
	@${MAKE} ${CHECK_JOB}.pdf; \
	python3 ${CHECK_DIR}check-settled.py --status $$? \
	  --sources "${CHECK_SOURCES}" ${CHECK_JOB} ${TEX_OUTDIR} ${CHECK_ENGINE}
	@ln -sf ${TEX_OUTDIR}/${CHECK_JOB}.pdf ${CHECK_JOB}.pdf
