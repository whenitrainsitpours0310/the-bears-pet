@echo off
title Stop Kanye Quote Bubble
python "%~dp0run.py" --stop
if errorlevel 1 pause
