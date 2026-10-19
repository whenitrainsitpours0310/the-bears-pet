@echo off
title Enable Kanye Quote Bubble Startup
python "%~dp0startup.py" install
if errorlevel 1 pause
