@echo off
cd /d "%~dp0"
if exist ".venv\Scripts\activate.bat" (
  call ".venv\Scripts\activate.bat"
  python -m streamlit run viewer/app.py
) else (
  python -m streamlit run viewer/app.py
)
