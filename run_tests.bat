@echo off
echo Setting PYTHONPATH...
set PYTHONPATH=%~dp0
echo.
echo 🎯 NOTION 학습 관리 시스템 테스트 실행
echo ========================================
echo.

echo [1] 단위 테스트 실행...
python -m pytest tests/test_code_analysis_service.py -v --tb=short

echo.
echo [2] 통합 테스트 실행...
python -m pytest tests/integration/ -v --tb=short

echo.
echo [3] 언어 테스트 실행...
python -m pytest tests/language_tests/ -v --tb=short

echo.
echo All tests completed.
pause 