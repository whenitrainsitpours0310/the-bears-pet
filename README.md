# The Bears Pet

Three Kanye-inspired bear atlases for ChatGPT Pets, plus a Windows quote-bubble companion. The bubble recognizes a visible Dropout, Late Registration, or Graduation bear near the mouse pointer and cycles through 75 sourced quotes.

## Contents

- `Pets/Dropout Bear/qa/look/spritesheet-v2-v3-clean.png`
- `Pets/Late Registration Bear/qa/spritesheet-extended-v4.png`
- `Pets/Graduation Bear/qa/extended-atlas-final.png`
- `Pets/Quote Bubble/` — local overlay and launchers

Each atlas is a 1536 × 2288 RGBA sprite sheet. The quote bubble is a separate local process. Copying this repository does not install or select a pet inside ChatGPT.

## Quote bubble on Windows

Install Python 3.10 or newer, then run from this repository folder:

```powershell
python -m pip install -r requirements.txt
python "Pets/Quote Bubble/run.py"
```

With a bear already visible in the ChatGPT desktop app, hover over it to show a quote. You can also double-click `Pets/Quote Bubble/启动名言气泡.cmd`. `启动宠物和气泡.cmd` sends ChatGPT's default Win+Alt+P shortcut to show the pet. The `.cmd` launchers expect `python` on `PATH`.

See [the bubble guide](Pets/Quote%20Bubble/README.md) for startup and stop commands. The overlay reads screen pixels near the pointer; it stays hidden if the bear is covered or cannot be identified.

## Check

```powershell
cd "Pets/Quote Bubble"
python -m unittest test_bubble.py -v
```

The bubble's first image search is more expensive than tracking an already recognized bear. Detection runs in a worker thread so the overlay window remains responsive while the search completes. ChatGPT downloads and renders the pets itself; network or client-side loading delays are outside this companion's control.
