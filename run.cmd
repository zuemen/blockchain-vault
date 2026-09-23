@echo off
rem Windows 用的指令入口（取代 Makefile）。用法：run peek / run update / run status ...
setlocal
rem 主控台切到 UTF-8，本檔內的中文說明才不會亂碼
chcp 65001 >nul
rem 讓 Python 輸出以 UTF-8 編碼，解決中文亂碼
set PYTHONIOENCODING=utf-8
rem 無論從哪個目錄呼叫，都切回 vault 根目錄
cd /d "%~dp0"
if "%1"=="peek"   ( python scripts\fetch_news.py --dry-run --hours 36 & goto end )
if "%1"=="fetch"  ( python scripts\fetch_news.py --hours 36 --top 8 & goto end )
if "%1"=="build"  ( python scripts\build_site.py & goto end )
if "%1"=="update" ( python scripts\fetch_news.py --hours 36 --top 8 && python scripts\build_site.py & goto end )
if "%1"=="status" ( python scripts\status.py & goto end )
if "%1"=="unread" ( python scripts\status.py --unread & goto end )
if "%1"=="serve"  ( python scripts\build_site.py && cd site && python -m http.server 8080 & goto end )
echo 用法: run [peek^|fetch^|build^|update^|status^|unread^|serve]
:end
