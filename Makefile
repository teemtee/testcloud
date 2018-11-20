# Copyright 2018, Red Hat, Inc.
# License: GPL-2.0+ <http://spdx.org/licenses/GPL-2.0+>
# See the LICENSE file for more details on Licensing

#######################################################################
#      _____            _        _ _           _   _                  #
#     / ____|          | |      (_) |         | | (_)                 #
#    | |     ___  _ __ | |_ _ __ _| |__  _   _| |_ _ _ __   __ _      #
#    | |    / _ \| '_ \| __| '__| | '_ \| | | | __| | '_ \ / _` |     #
#    | |___| (_) | | | | |_| |  | | |_) | |_| | |_| | | | | (_| |     #
#     \_____\___/|_| |_|\__|_|  |_|_.__/ \__,_|\__|_|_| |_|\__, |     #
#                                                           __/ |     #
#     If you want to add/fix anything here, please create  |___/      #
#     PR at qa-make https://pagure.io/fedora-qa/qa-make               #
#                                                                     #
#######################################################################

# Allows to print variables, eg. make print-SRC
print-%  : ; @echo $* = $($*)

# Get variables from Makefile.cfg
SRC=$(shell grep -s SRC Makefile.cfg | sed 's/SRC=//')
VENV=$(shell grep -s VENV Makefile.cfg | sed 's/VENV=//')
MODULENAME=$(shell grep -s MODULENAME Makefile.cfg | sed 's/MODULENAME=//')

# Try to detect SRC in case we didn't find Makefile.cfg
ifeq ($(SRC),)
SRC=$(shell rpmspec -q --queryformat="%{NAME}\n" *.spec | head -1)
SPECNUM=$(shell ls -1 *.spec | wc -l)
ifneq ($(SPECNUM),1)
$(error Make sure you have either one spec file in the directory or configure it in Makefile.cfg)
endif
endif

# Variables used for packaging
SPECFILE=$(SRC).spec
BASEARCH:=$(shell uname -i)
DIST:=$(shell rpm --eval '%{dist}')
TARGETVER:=$(shell lsb_release -r |grep -o '[0-9]*')
TARGETDIST:=fc$(TARGETVER)
VERSION:=$(shell rpmspec -q --queryformat="%{VERSION}\n" $(SPECFILE) | head -1)
RELEASE:=$(shell rpmspec -q --queryformat="%{RELEASE}\n" $(SPECFILE) | head -1 | sed 's/$(DIST)/\.$(TARGETDIST)/g')
NVR:=$(SRC)-$(VERSION)-$(RELEASE)
GITBRANCH:=$(shell git rev-parse --abbrev-ref HEAD)
BUILDTARGET:=fedora-$(TARGETVER)-x86_64
KOJITARGET:=$(shell echo $(TARGETDIST) | sed 's/c//' | sed 's/el/epel-/')

.PHONY: update-makefile
update-makefile:
	curl --fail https://pagure.io/fedora-qa/qa-make/raw/master/f/Makefile -o Makefile.new
	if ! cmp Makefile Makefile.new ; then mv Makefile.new Makefile ; fi

.PHONY: test
.ONESHELL: test
test: $(VENV)
	set -e
	source $(VENV)/bin/activate;
	TEST='true' py.test --cov-report=term-missing --cov $(MODULENAME);
	deactivate

.PHONY: test-ci
.ONESHELL: test-ci
test-ci: $(VENV)
	set -e
	source $(VENV)/bin/activate
	TEST='true' py.test --cov-report=xml --cov $(MODULENAME)
	deactivate

.PHONY: pylint
pylint:
	pylint -f parseable $(SRC) | tee pylint.out

.PHONY: pep8
pep8:
	pep8 $(SRC)/*.py $(SRC)/*/*.py | tee pep8.out

.PHONY: ci
ci: test-ci pylint pep8

.PHONY: docs
docs:
	sphinx-build  -b html -d docs/_build/doctrees docs/source docs/_build/html

.PHONY: clean
clean:
	rm -rf dist
	rm -rf $(SRC).egg-info
	rm -rf build
	rm -f pep8.out
	rm -f pylint.out

.PHONY: archive
archive: $(SRC)-$(VERSION).tar.gz

.PHONY: $(SRC)-$(VERSION).tar.gz
$(SRC)-$(VERSION).tar.gz:
	git archive $(GITBRANCH) --prefix=$(SRC)-$(VERSION)/ | gzip -c9 > $@
	mkdir -p build/$(VERSION)-$(RELEASE)
	mv $(SRC)-$(VERSION).tar.gz build/$(VERSION)-$(RELEASE)/

.PHONY: srpm
srpm: archive
	mock -r $(BUILDTARGET) --buildsrpm --spec $(SPECFILE) --sources build/$(VERSION)-$(RELEASE)/
	cp /var/lib/mock/$(BUILDTARGET)/result/$(NVR).src.rpm build/$(VERSION)-$(RELEASE)/

.PHONY: build
build: srpm
	mock -r $(BUILDTARGET) --no-clean --rebuild build/$(VERSION)-$(RELEASE)/$(NVR).src.rpm
	cp /var/lib/mock/$(BUILDTARGET)/result/*.rpm build/$(VERSION)-$(RELEASE)/

.PHONY: scratch
scratch: srpm
	koji build --scratch $(KOJITARGET) build/$(VERSION)-$(RELEASE)/$(NVR).src.rpm

.PHONY: nvr
nvr:
	@echo $(NVR)

.PHONY: cleanvenv
cleanvenv:
	rm -rf $(VENV)

.PHONY: virtualenv
virtualenv: $(VENV)

.PHONY: $(VENV)
.ONESHELL: $(VENV)
$(VENV):
	virtualenv --system-site-packages $(VENV)
	set -e
	source $(VENV)/bin/activate
	pip install -r requirements.txt
	deactivate
