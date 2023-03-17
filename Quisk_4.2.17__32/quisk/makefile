.PHONY: quisk

quisk:
	@echo 'Please specify either quisk2 or quisk3 for Python 2 or 3'

quisk2:
	python2 setup.py build_ext --force --inplace
	@echo

quisk3:
	python3 setup.py build_ext --force --inplace
	@echo

soapy2:
	(cd soapypkg; make soapy2)

soapy3:
	(cd soapypkg; make soapy3)

afedrinet2:
	(cd afedrinet; make afedrinet2)

afedrinet3:
	(cd afedrinet; make afedrinet3)

perseus2:
	(cd perseuspkg; make perseus2)

perseus3:
	(cd perseuspkg; make perseus3)
