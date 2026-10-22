@echo off
title Road Variant Comparator
echo ========================================================
echo   Lancement de Road Variant Comparator (Streamlit)
echo ========================================================
echo.
cd /d "%~dp0"
python -m streamlit run src/app.py
pause
