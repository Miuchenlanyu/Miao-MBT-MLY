@echo off
chcp 65001 >nul
cd /d "%~dp0"
title 同步到 GitHub - Miao-MBT-MLY

echo ============================================
echo   同步到 GitHub：Miao-MBT-MLY
echo   目录：%cd%
echo ============================================
echo.

where git >nul 2>nul
if errorlevel 1 (
  echo [错误] 未检测到 git，请先安装 Git 并把它加入 PATH
  echo.
  pause
  exit /b 1
)

git rev-parse --is-inside-work-tree >nul 2>nul
if errorlevel 1 (
  echo [错误] 当前目录不是 git 仓库，请检查 .git 是否存在
  echo.
  pause
  exit /b 1
)

echo ---- 当前状态 ----
git status -sb
echo.

set /p msg=请输入提交说明（直接回车用默认说明）: 
if "%msg%"=="" set msg=update %date% %time%
echo.

echo ---- 1/3 暂存文件 ----
git add -A
if errorlevel 1 goto err

git diff --cached --quiet
if errorlevel 1 (
  echo ---- 2/3 提交 ----
  git commit -m "%msg%"
  if errorlevel 1 goto err
) else (
  echo 没有需要提交的变更，跳过提交
)

echo ---- 3/3 拉取并推送到 main ----
git pull --no-edit origin main
git push origin main
if errorlevel 1 goto err

echo.
echo [完成] 已同步到 GitHub
echo.
pause
exit /b 0

:err
echo.
echo [失败] 上面有错误。常见原因：
echo   1. 未授权或令牌过期（重新登录 / 换新令牌）
echo   2. 网络不通
echo   3. 远端有新提交导致冲突（先手动 git pull 处理）
echo.
pause
exit /b 1
