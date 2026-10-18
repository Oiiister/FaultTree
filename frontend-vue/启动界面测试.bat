@echo off
chcp 65001 >nul
echo ========================================
echo    前端界面风格测试 - 启动程序
echo ========================================
echo.
echo 正在启动服务器...
echo 端口：3001
echo 访问地址：http://localhost:3001/
echo.
echo 提示：
echo - 按 Ctrl+C 可停止服务器
echo ========================================
echo.

cd /d "%~dp0"
npm run dev

pause
