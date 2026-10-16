@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================
echo   Gamewiki 角色跟进 - 本地启动
echo   服务地址: http://127.0.0.1:11002
echo   浏览器将自动打开（若未打开请手动访问）
echo ============================================
echo.
echo 正在复制大头照并生成数据快照...
python server.py --export
echo.
echo 启动服务中...
start "" http://127.0.0.1:11002
python server.py
pause
