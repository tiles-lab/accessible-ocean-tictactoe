# Sanctuary Restoration – Interactive Habitat Exhibit

An interactive exhibit where visitors restore a marine sanctuary map, one zone at a time, by turning physical cubes on a 4×4 board so each cube shows the right seabed habitat.

An overhead webcam watches the board. It uses:
- **ArUco markers** to locate the board,
- **MediaPipe hand tracking** to detect fingertip touches,
- **HSV color detection** to read which habitat face each cube is showing.

The four habitats are **Flat sand**, **Rippled sand**, **Sparse live bottom** and **Dense live bottom**. Each has its own sound.

---

## How it works

1. **Sanctuary map (macro view).** A map with 5 empty zones. Staff (or a button) picks a zone with keys `1`–`5`.
2. **Zone board (micro view).** The physical 4×4 board now stands for that zone. Visitors:
   - **touch a cube with one finger** to hear the habitat sound expected at that spot,
   - **turn the cube** to the face they think matches,
   - **touch it with two fingers** to check the answer. A correct cube is revealed on screen.
3. **Legend row.** A row of 4 squares under the board. Touching one plays a short sample of that habitat's sound, then a spoken description.
4. When all 16 cubes are correct, the zone is restored on the map. Restoring all 5 zones completes the sanctuary.

---

## Requirements

**Software**
- Python **3.10** (tested with 3.10.9). MediaPipe's `solutions` API used here does not support every newer Python version.
- macOS, Windows or Linux

**Hardware**
- A webcam mounted **above the board, looking straight down**
- The physical board:
  - a 4×4 grid of colored habitat cubes
  - the legend row of 4 habitat squares under the grid, in this order left → right: Flat sand, Rippled sand, Sparse live bottom, Dense live bottom
  - two ArUco markers from the `DICT_4X4_100` dictionary: **ID 45** at the top-left corner and **ID 57** at the bottom-right corner
- Speakers

---

## Getting the latest version (for collaborators)

When someone on the team improves the exhibit, they upload ("push") their changes to GitHub. To get those changes on your computer, you download them ("pull"). It takes about a minute, and you can do it any time, for example before testing or setting up the exhibit.

You don't need to know any programming. You'll type a few commands in **Terminal**, an app that comes with every Mac.

### Every time you want the latest version

1. **Open Terminal.** Press `Cmd + Space`, type `Terminal`, and press `Enter`.

2. **Go to the project folder.** Type `cd` followed by a space (don't press `Enter` yet). Then, from Finder, drag the `accessible-ocean-tictactoe` folder into the Terminal window. Its location appears after `cd`. Now press `Enter`.

3. **Download the latest changes.** Type this and press `Enter`:
   ```bash
   git pull
   ```
   - `Already up to date.` means you already had the newest version. You can stop here.
   - A list of file names with `+` and `-` signs means it worked: you now have the newest version.
   - Anything that says `error` or `CONFLICT`: see the next section.

4. **Update the Python packages.** This is safe to run every time, and quick when nothing has changed. Type these two lines, pressing `Enter` after each:
   ```bash
   source .venv/bin/activate
   python -m pip install -r requirements.txt
   ```

5. **Done.** Start the exhibit as usual (see [Step 2](#step-2--run-the-exhibit)).

**Your calibration is kept.** Your color calibration (`hsv_ranges.json`) and camera picture settings (`camera_settings.json`) belong to your computer only. `git pull` never changes or deletes them, so you don't need to recalibrate after updating, unless the lighting or the camera changed.

### If `git pull` shows an error

Nothing is broken. The exhibit still works with the version you had. Find the message you see:

| Message | What to do |
|---|---|
| `Your local changes to the following files would be overwritten` or `Please commit your changes or stash them` | Some files on your computer were edited. Put those edits aside, then pull again: type `git stash`, press `Enter`, then `git pull`, press `Enter`. Your edits aren't deleted: they're saved and can be restored with `git stash pop`. |
| `not a git repository` | Terminal isn't in the project folder. Redo step 2. |
| A window asks to install "command line developer tools" | Click **Install**, wait for it to finish, then redo step 3. This happens only once. |
| `CONFLICT`, `divergent branches`, or anything else | Don't try to fix it. Type `git merge --abort`, press `Enter` (if it says there's nothing to abort, that's fine), then send a screenshot of the Terminal window to the project lead. |

**Tip:** to avoid these errors, don't edit the project's files directly. Settings that change per room (colors, camera picture) are saved in the two files above, which are never touched by updates.

### Prefer clicking to typing?

Install [GitHub Desktop](https://desktop.github.com). Choose **File → Add Local Repository**, and select the `accessible-ocean-tictactoe` folder. After that, click **Fetch origin** and then **Pull origin** to get the latest version. You still need step 4 above after pulling.

---

## Setup

First time only. On a computer that already has the project, see [Getting the latest version](#getting-the-latest-version-for-collaborators) instead.

```bash
git clone https://github.com/tiles-lab/accessible-ocean-tictactoe.git
cd accessible-ocean-tictactoe

python3.10 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

**macOS:** the first time you run a script, macOS asks for camera access for your Terminal (or VS Code). Allow it, then restart the terminal.

### Choosing the camera

Both scripts ask which camera to use when they start, and list the cameras by name (on a Mac this needs `pyobjc-framework-AVFoundation`, which `requirements.txt` installs). Press **`v`** while a script is running to switch to the next camera.

To skip the question (needed for the exhibit, so it starts on its own), pass `--camera`, or set `CAMERA_INDEX` near the top of the script:

| `--camera` value | Uses |
|---|---|
| `orbbec` | the **Orbbec Gemini 2**'s color camera |
| part of a name, e.g. `FaceTime` | the camera whose name contains that text |
| a number, e.g. `0` | that camera number |

```bash
python hsv_calibration_tool.py --camera orbbec
python tictactoe_prototype8.py --camera orbbec
```

On a Mac, prefer `orbbec` or a name over a number: camera numbers shift when an iPhone (Continuity Camera) or Desk View camera appears or disappears.

### Orbbec Gemini 2

The Gemini's **color** camera is reached through the Orbbec SDK. Install it once, **with `--no-deps`**: its dependencies include `opencv-python`, which would replace the `opencv-contrib-python` this project uses and break it.

```bash
python -m pip install --no-deps pyorbbecsdk2
```

**On a Mac**, macOS only exposes the Gemini's IR camera (greyscale) to normal programs. The SDK is the only way to get color, and it must run as administrator (Orbbec requires this on macOS):

```bash
sudo -E .venv/bin/python hsv_calibration_tool.py --camera orbbec
sudo -E .venv/bin/python tictactoe_prototype8.py --camera orbbec
```

- Use `.venv/bin/python` (not just `python`): `sudo` doesn't keep your activated environment.
- `sudo` asks for your Mac password. Run the commands from the project folder.
- Files the scripts write (e.g. `hsv_ranges.json`) are handed back to your user account, so later non-sudo runs can still update them.
- Don't pick the "Orbbec Gemini 2 IR Camera" entry from the list: it's greyscale, so color calibration won't work with it.

**On Windows/Linux**, `--camera orbbec` works without administrator rights (through OpenCV's built-in Orbbec support or the SDK).

To see exactly which cameras your computer offers, and whether each one gives a color or greyscale image, run `python camera_select.py`. It also saves a snapshot from each camera.

Close OrbbecViewer before running the scripts. Only one program can use the camera at a time.

---

## Step 1 – Calibrate the colors

Cube colors look different under different lighting. Calibrate **every time the exhibit moves to a new room or the lighting changes.**

```bash
python hsv_calibration_tool.py
```

1. Put the board under the camera with good, even lighting.
   **Orbbec Gemini:** if the picture looks too bright (washed-out colors, or areas shown in **red** = over-exposed), fix that first with these keys:

   | Keys | Adjust |
   |------|--------|
   | `[` / `]` | exposure down / up (the main fix for a too-bright picture) |
   | `;` / `'` | gain down / up |
   | `,` / `.` | brightness down / up |
   | `e` | auto-exposure on / off |

   Changing exposure or gain turns auto-exposure off, so the picture stays fixed during the exhibit. Settings are saved to `camera_settings.json` and applied automatically by the game. If you change them later, recalibrate the colors.
2. Press a key to choose which habitat you are sampling:

   | Key | Habitat |
   |-----|---------|
   | `f` | Flat sand |
   | `r` | Rippled sand |
   | `s` | Sparse live bottom |
   | `d` | Dense live bottom |

3. **Click** on a cube face of that habitat, then press **SPACE** to save the sample.
4. Repeat on several cubes and different spots (center, edges, slightly shadowed areas). Aim for **5–10 samples per habitat**; at least 2 are required.
5. Repeat for all four habitats.
6. Press **`p`**. The ranges are printed in the terminal and saved to **`hsv_ranges.json`** in the repo folder.
7. Press **ESC** to quit.

That's it: the exhibit loads `hsv_ranges.json` automatically at startup, so there is no code to edit. Running the calibration again overwrites the file.

If `hsv_ranges.json` doesn't exist, or a habitat wasn't sampled, the default ranges in `COLOR_HSV_RANGES` (top of `tictactoe_prototype8.py`) are used instead. The terminal tells you at startup which one was loaded.

---

## Step 2 – Run the exhibit

Run from the repo root, so the sound files are found:

```bash
python tictactoe_prototype8.py
```

Two windows open:
- **Aquarium Map Display**, the visitor-facing screen
- **Camera View (Debug)**, the camera feed with the detected grid, markers and fingertips drawn on it

At startup, the terminal prints an audio check. Every sound should show `[OK]`. `[MISSING]` means a file isn't where the code expects it.

### Keyboard controls

| Key | Where | Action |
|-----|-------|--------|
| `1`–`5` | Map | Start restoring that zone |
| `b` | Board | Go back to the map without finishing the zone |
| `c` | Anywhere | Forget the saved marker positions and re-detect them. Use this if the board or camera was moved |
| `SPACE` | Anywhere | Switch all habitat sounds between the original and alternate versions |
| `ESC` | Anywhere | Quit |

### Touch controls (on the physical board)

| Gesture | Result |
|---------|--------|
| One finger on a cube | Plays that spot's habitat sound in a loop while the finger stays |
| Two fingers on a cube | Checks if the cube shows the correct habitat |
| Finger on a legend square | Plays the habitat sample, then its description |

---

## Project structure

```
.
├── tictactoe_prototype8.py        # Main exhibit
├── hsv_calibration_tool.py        # Color calibration tool
├── camera_select.py               # Camera choice (used by both). Run it alone to list your cameras
├── requirements.txt
├── hsv_ranges.json                # Color calibration (created by the calibration tool, not shared)
├── camera_settings.json           # Orbbec picture settings (created by the calibration tool, not shared)
├── Holes_map_new_colors.png       # Sanctuary map with empty zones
├── og_map_new_colors.png          # Fully restored sanctuary map
├── Sounds_VF/
│   ├── BASIC_v3/                  # Habitat sound loops
│   └── SPEECH_US_v1/              # Alternate habitat sounds
├── sounds/                        # Legend descriptions, correct/wrong cues
└── narration/                     # Zone-complete and final narrations
```

---

## Configuration

All settings are constants at the top of `tictactoe_prototype8.py`:

| Setting | What it controls |
|---------|------------------|
| `COLOR_HSV_RANGES` | Fallback color ranges, used only when `hsv_ranges.json` is missing or incomplete |
| `ZONE_HABITAT_LAYOUTS` | The correct habitat for each of the 16 cells in each zone |
| `GRID_OFFSET_*` | Where the 4×4 grid sits between the two markers |
| `LEGEND_*` | Position and size of the legend row |
| `HABITAT_SOUND_PATHS` | Which audio file plays for what |
| `SOUND_TRIM` | Make individual sounds louder or quieter |
| `DWELL_TIME` | How long a finger must stay before something happens |
| `SHOW_EVAL_DEBUG` | Show the crop and mask used for each color check |

---

## Troubleshooting

**Wrong camera opens or "could not open camera"**
Launch with `--camera orbbec` (or a part of the camera's name), see [Choosing the camera](#choosing-the-camera). Run `python camera_select.py` to see every camera your computer offers, and whether each gives a color or a greyscale image.

**`[MISSING]` sounds at startup, or no voice when a zone is completed**
The audio check at startup lists every sound file. Check that each `[MISSING]` file exists at the path shown. `zone_select` is optional and may be missing. If the zone narrations are missing, the startup log also shows a `WARNING` line naming them.

**"Waiting for ArUco markers 45 and 57..."**
Both markers must be visible, flat and well lit at least once. After that, their positions are remembered even when a hand covers them.

**Cubes are judged wrong even when they're right**
Recalibrate (Step 1) under the current lighting, and check that the startup log says `Loaded HSV calibration from ...hsv_ranges.json`. Turn on `SHOW_EVAL_DEBUG` to see exactly which pixels were checked.

**Fingers aren't detected**
Make sure the hand is well lit and the fingers are extended, not curled.