#
# Copyright 2018, Red Hat, Inc.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
#

# general variables
SRC:=testcloud

# Variables used for packaging
SPECFILE:=$(SRC).spec
BASEARCH:=$(shell uname -i)
DIST:=$(shell rpm --eval '%{dist}')
VERSION:=$(shell rpmspec -q --queryformat="%{VERSION}\n" $(SPECFILE) | uniq)
RELEASE:=$(subst $(DIST),,$(shell rpmspec -q --queryformat="%{RELEASE}\n" $(SPECFILE) | uniq))
NVR:=$(SRC)-$(VERSION)-$(RELEASE)
GITBRANCH:=$(shell git rev-parse --abbrev-ref HEAD)
TARGETVER:=$(shell lsb_release -r |grep -o '[0-9]*')
TARGETDIST:=fc$(TARGETVER)
BUILDTARGET:=fedora-$(TARGETVER)-x86_64

.PHONY: pylint
pylint:
	pylint -f parseable $(SRC) | tee pylint.out

.PHONY: pep8
pep8:
	pep8 $(SRC)/*.py $(SRC)/*/*.py | tee pep8.out

.PHONY: ci
ci: pylint pep8

.PHONY: docs
docs:
	cd docs && $(MAKE) clean && $(MAKE) html

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

.PHONY: mocksrpm
mocksrpm: archive
	mock -r $(BUILDTARGET) --buildsrpm --spec $(SPECFILE) --sources .
	cp /var/lib/mock/$(BUILDTARGET)/result/$(NVR).$(TARGETDIST).src.rpm .

.PHONY: mockbuild
mockbuild: mocksrpm
	mock -r $(BUILDTARGET) --no-clean --rebuild $(NVR).$(TARGETDIST).src.rpm
	cp /var/lib/mock/$(BUILDTARGET)/result/$(NVR).$(TARGETDIST).noarch.rpm .

.PHONY: nvr
nvr:
	@echo $(NVR)
