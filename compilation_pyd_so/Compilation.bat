@echo off
start /b "" python setup.py build_ext -c mingw32 --inplace --force
pause