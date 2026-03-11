.PHONY: all paper clean

all:
	@echo "Use 'make paper' to build PDF"

paper:
	mkdir -p build
	pdflatex -output-directory=build village_life_needs.tex
	pdflatex -output-directory=build village_life_needs.tex

clean:
	rm -rf build/
