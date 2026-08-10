PACKAGES := cyclo-agent dcomp cyclo-provider-pooler

.PHONY: fetch build lint test clean $(PACKAGES)

fetch:
	./tools/fetch-sources $(PACKAGES)

build:
	./tools/build-packages $(PACKAGES)

cyclo-agent dcomp cyclo-provider-pooler:
	./tools/build-packages $@

lint:
	python3 -m unittest discover -s tests -v

test: lint
	python3 -m py_compile tools/fetch-sources tools/build-packages
	for script in $$(find packages -path '*/debian/tests/*' -type f -perm -0100); do sh -n "$$script"; done

clean:
	rm -rf .sources artifacts
