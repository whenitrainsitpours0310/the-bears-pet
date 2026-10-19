"""Manage this user's interactive Windows logon task for the quote bubble."""

from __future__ import annotations

import argparse
import subprocess
import sys
import winreg
from pathlib import Path


ROOT = Path(__file__).resolve().parent
TASK_NAME = "KanyeQuoteBubble"
OLD_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def ps_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def powershell(script: str) -> str:
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
         "$ErrorActionPreference = 'Stop'; " + script],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def remove_old_run_entry() -> None:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, OLD_RUN_KEY, 0,
                            winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, TASK_NAME)
    except FileNotFoundError:
        pass


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("install", "remove", "status"))
    action = parser.parse_args().action
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    if not pythonw.is_file():
        raise SystemExit("pythonw.exe was not found beside the current Python interpreter.")
    task = ps_quote(TASK_NAME)
    executable = ps_quote(str(pythonw))
    arguments = ps_quote(f'"{ROOT / "launch.py"}" --login-startup')
    directory = ps_quote(str(ROOT))

    if action == "install":
        powershell(
            "$user = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name; "
            f"$action = New-ScheduledTaskAction -Execute {executable} "
            f"-Argument {arguments} -WorkingDirectory {directory}; "
            "$trigger = New-ScheduledTaskTrigger -AtLogOn -User $user; "
            "$principal = New-ScheduledTaskPrincipal -UserId $user "
            "-LogonType Interactive -RunLevel Limited; "
            "$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable "
            "-AllowStartIfOnBatteries -DontStopIfGoingOnBatteries "
            "-MultipleInstances IgnoreNew "
            "-ExecutionTimeLimit (New-TimeSpan -Seconds 0) "
            "-RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1); "
            f"Register-ScheduledTask -TaskName {task} -Action $action "
            "-Trigger $trigger -Principal $principal -Settings $settings -Force "
            "| Out-Null"
        )
        remove_old_run_entry()
        print("Quote bubble logon task installed for this user.")
    elif action == "remove":
        powershell(
            f"Unregister-ScheduledTask -TaskName {task} -Confirm:$false "
            "-ErrorAction SilentlyContinue"
        )
        remove_old_run_entry()
        print("Quote bubble Windows startup disabled.")
    else:
        state = powershell(
            f"$task = Get-ScheduledTask -TaskName {task} "
            "-ErrorAction SilentlyContinue; "
            "if ($null -eq $task) { 'disabled' } "
            "else { $task.State.ToString(); "
            f"[string](($task.Actions[0].Execute -eq {executable}) -and "
            f"($task.Actions[0].Arguments -eq {arguments})) }}"
        ).splitlines()
        if not state or state[0] == "disabled":
            print("Quote bubble Windows startup is disabled.")
            return
        print(f"Quote bubble Windows startup task is {state[0]}.")
        print("Command matches this installation:", len(state) >= 2 and state[1] == "True")


if __name__ == "__main__":
    main()
