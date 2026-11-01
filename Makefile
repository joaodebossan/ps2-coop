.PHONY: run test build appimage package icons clean

run:
	python3 app.py --game .

test:
	python3 -m unittest discover -s tests -v

build:
	python3 build.py

appimage: build
	bash tools/build_appimage.sh

package:
	python3 tools/package.py

icons:
	python3 tools/make_icons.py

clean:
	rm -rf build dist __pycache__ ps2coop/__pycache__ tests/__pycache__
