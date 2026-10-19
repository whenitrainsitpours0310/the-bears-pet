@echo off
title Disable Kanye Quote Bubble Startup
python "%~dp0startup.py" remove
if errorlevel 1 pause
