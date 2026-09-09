@echo off
chcp 65001 > nul
echo 🚀 AI 트레이딩 팀 대시보드를 실행합니다...
cd /d "%~dp0"
python -m streamlit run app.py
pause