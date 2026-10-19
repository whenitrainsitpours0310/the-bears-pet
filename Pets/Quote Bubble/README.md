# Kanye quote bubble

A small Windows companion for the ChatGPT desktop pet. Its detector uses the
three final v2 atlases uploaded on 2026-10-17, including Graduation's active
work animation frames.
Hover over the visible
Dropout, Late Registration, or Graduation bear to show one of the 75 sourced
quotes in `quotes.json`. The quote changes every 10 seconds while the pointer
stays over the bear. Moving the pointer away hides the bubble. Quotes do not
repeat within a 75-quote round.

## Run

If the pet is already visible, double-click `启动名言气泡.cmd` to start the bubble.
If the pet is hidden, `启动宠物和气泡.cmd` also sends ChatGPT's default
**Win+Alt+P** shortcut. The launchers start a background process, so no
terminal needs to stay open. Double-click `停止名言气泡.cmd` to stop it.
The ChatGPT desktop app must already be running. If you changed the Show pet
shortcut in ChatGPT settings, start the bubble alone and summon the pet with
your chosen shortcut.

From the project root:

```powershell
python -m pip install Pillow numpy
python "Pets/Quote Bubble/run.py"
```

When running `run.py` directly, keep that terminal open and press **Ctrl+C**
to stop. Double-clicking the launcher again summons the pet without creating a
second bubble process.
The bubble is always on top but does not capture mouse input. No ChatGPT pet
file or setting is changed.

The detector reads pixels near the pointer, so the bear must be visible and
not covered by another window. It recognizes pet scales from 50% to 150% of
the final 192 × 208 atlas cells. The first acquisition can take around one
second; subsequent tracking of the same bear is faster. If the pet is hidden
or cannot be recognized, the bubble stays hidden.

This is a local companion process. A current-user Windows logon task launches
the bubble after the desktop and ChatGPT are ready. The task stays active while
the bubble runs and retries if the process crashes. Double-click
`启用开机自启.cmd` to restore the task or `禁用开机自启.cmd` to remove it.
Login startup starts the bubble; the pet is shown separately by ChatGPT or the
combined manual launcher. The
bubble remains invisible until the pointer hovers over a visible bear. If it
does not start, inspect `runtime.log` in this folder for the Python error.

## Edit quotes

Edit `quotes.json`. Each entry needs `text`, `source`, and `url`. The URL is
kept for provenance; the click-through bubble displays only the source name.
The longer quotes automatically make the bubble taller so the attribution
remains visible.
