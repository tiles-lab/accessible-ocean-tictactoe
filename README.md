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

## Setup

```bash
git clone <repo-url>
cd <repo-folder>

python3.10 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

**macOS:** the first time you run a script, macOS asks for camera access for your Terminal (or VS Code). Allow it, then restart the terminal.

---

## Step 1 – Calibrate the colors

Cube colors look different under different lighting. Calibrate **every time the exhibit moves to a new room or the lighting changes.**

```bash
python hsv_calibration_tool.py
```

1. Put the board under the camera with good, even lighting.
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
├── requirements.txt
├── hsv_ranges.json                # Color calibration (created by the calibration tool)
├── Holes_map_new_colors.png       # Sanctuary map with empty zones
├── og_map_new_colors.png          # Fully restored sanctuary map
├── Sounds_VF/
│   ├── BASIC_v3/                  # Habitat sound loops
│   └── SPEECH_US_v1/              # Alternate habitat sounds
├── sounds/                        # Legend descriptions, correct/wrong cues
└── tic_tac_toe/narration/         # Zone-complete and final narrations
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
The main script tries camera indexes 1, 0 and 2. The calibration tool only uses index 1. If you have a single built-in camera, change `cv2.VideoCapture(1)` to `cv2.VideoCapture(0)` in `hsv_calibration_tool.py`.

**`[MISSING]` sounds at startup**
Run the script from the repo root, and check that the audio folders were cloned.

**"Waiting for ArUco markers 45 and 57..."**
Both markers must be visible, flat and well lit at least once. After that, their positions are remembered even when a hand covers them.

**Cubes are judged wrong even when they're right**
Recalibrate (Step 1) under the current lighting, and check that the startup log says `Loaded HSV calibration from ...hsv_ranges.json`. Turn on `SHOW_EVAL_DEBUG` to see exactly which pixels were checked.

**Fingers aren't detected**
Make sure the hand is well lit and the fingers are extended, not curled.
