@echo off
echo Setting PYTHONPATH...
set PYTHONPATH=%~dp0
echo Running all tests...
python -m pytest tests/test_code_analysis_service.py -v --tb=short
echo Test completed.
pause 