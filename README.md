# WoW Classic Fishing Bot

An automated fisher for **World of Warcraft Classic**. It casts your fishing
line, spots the bobber, waits for the splash (the bite), loots the catch, and
repeats — indefinitely and hands-free. Every action is deliberately randomized
and given natural mouse motion so the behavior reads like a real, slightly
distractible person rather than a machine.

```
Cast  ->  find bobber  ->  hover & wait for splash  ->  react & loot  ->  repeat
                                                    \-> take breaks, get "distracted"
```

> ⚠️ **Heads up:** Automating gameplay violates Blizzard's Terms of Service and
> can get your account banned. You asked for this and accept that risk — this
> README states it plainly so nobody is surprised. Use it on an account you're
> willing to lose. This is for personal, educational use.

---

## How it works

| Stage | What happens |
|-------|--------------|
| **Cast** | Presses your fishing hotbar key (default `8`) after a short, random hesitation. |
| **Find bobber** | Locates the bobber in a screen region you calibrate. Two strategies (below). |
| **Wait for bite** | Detects the splash by **sound** (WASAPI loopback) or **pixel change**. |
| **Loot** | After a human-like reaction delay, moves along a curved path and shift-right-clicks the bobber. |
| **Stay human** | Randomized timing everywhere, cursor tremor while hovering, occasional distractions, periodic breaks, and a hard session time limit. |

### Bobber detection strategies
- **`cursor_scan`** (default, Windows): sweeps the mouse across the fishing area
  until Windows reports the cursor changed into WoW's *interact* cursor — i.e.
  the game itself tells us we're over the bobber. Very reliable and independent
  of water color or weather.
- **`template`** (cross-platform): OpenCV matches a saved screenshot of the
  bobber. Use this if you're not on Windows or prefer image matching.

### Splash (bite) detection
- **`sound`** (default, Windows): listens to the game's own audio for the splash
  transient — exactly how a human notices a bite. Robust to visuals.
- **`pixel`** (cross-platform): watches a small box around the bobber for the
  white splash foam.

---

## Anti-detection / humanization

Nothing the bot does is on a fixed clock. Specifically:

- **Bezier mouse paths** with ease-in/ease-out, a random sideways bow, and
  occasional **overshoot-then-correct** — no straight teleports.
- **Gaussian-jittered timing** for casts, reactions, and waits (variance scales
  with the delay).
- **Idle hand tremor**: the cursor micro-jitters while hovering the bobber.
- **Reaction delay** between seeing the splash and clicking (default 180–520 ms).
- **Distractions**: small random chance to drift the mouse away and pause.
- **Breaks**: every ~55–120 casts it "steps away" for 25–140 s.
- **Fumbles**: rare intentional misfires, like a person mis-timing a cast.
- **Session limit**: stops after a configurable number of minutes.
- **DirectX-correct input** via `pydirectinput` (hardware scan codes), which WoW
  actually registers — unlike naive key events.

Tune all of it in `config.yaml` under the `human:` section.

---

## Setup (Windows — recommended)

1. **Install Python 3.10+** from python.org (tick *Add to PATH*).
2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```
   On Windows this also pulls `pywin32` (cursor detection) and `PyAudioWPatch`
   (sound splash detection).
3. **In WoW:**
   - Set the display to **Windowed (Fullscreen)** — *not* exclusive fullscreen,
     or screen capture / input may not work.
   - Put your **Fishing** spell (or a `/cast Fishing` macro) on a hotbar key and
     set `keys.cast` in `config.yaml` to match.
   - Turn on **Auto Loot** (Interface → Controls) for clean pickups.
   - Equip a fishing pole, stand still, and face the water.
4. **Calibrate:**
   ```bash
   python calibrate.py
   ```
   Follow the prompts to mark the fishing region (and optionally capture a bobber
   image if you'll use the `template` strategy).
5. **Run:**
   ```bash
   python run.py
   ```
   The bot **starts paused**. Alt-tab back into WoW and press **F9** to begin.

### Controls
| Key | Action |
|-----|--------|
| **F9** | Pause / resume |
| **F10** | Quit |
| **Ctrl+C** (terminal) | Force quit |

---

## Configuration cheatsheet (`config.yaml`)

```yaml
keys:
  cast: "8"                # your Fishing hotbar key
region: [700, 300, 520, 380]   # set by calibrate.py — where the bobber lands
bobber:
  strategy: "cursor_scan"  # or "template"
splash:
  method: "sound"          # or "pixel"
  sound_threshold: 0.16    # raise if it triggers on background noise
human:
  reaction_ms: [180, 520]  # human delay before clicking the bite
  break_every_casts: [55, 120]
  max_session_minutes: 150
control:
  start_paused: true
  dry_run: false           # true = detect & log, never send input
```

The full, commented file is in `config.yaml`.

---

## Testing without touching the game

Run in **dry-run** mode to watch it detect casts/bobbers/splashes and log what it
*would* do, without ever pressing a key or clicking:

```bash
python run.py --dry-run
```

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| Keys/clicks do nothing in-game | Ensure `pydirectinput` is installed; use Windowed (Fullscreen); run the terminal **as Administrator** (WoW runs elevated for some setups). |
| Bobber never found (`cursor_scan`) | Confirm `pywin32` is installed; tighten `region` around the splash zone; lower `scan_step`. |
| Bobber never found (`template`) | Re-run `calibrate.py` hovering the bobber's center; lower `bobber.match_threshold`. |
| Splash never/always triggers (`sound`) | Adjust `splash.sound_threshold`; make sure game audio actually plays through the default output device. |
| Splash flaky (`pixel`) | Increase `pixel_watch_radius`; adjust `pixel_change_ratio`. |
| No hotkeys | Install `keyboard`; on some systems it needs Administrator to capture global keys. |

---

## Project layout

```
run.py               # entry point
calibrate.py         # interactive region / template setup
config.yaml          # all settings (commented)
requirements.txt
fishbot/
  bot.py             # main loop + control state machine
  config.py          # typed config loading with defaults + deep-merge
  humanize.py        # timing jitter, Bezier paths, breaks — the "human" layer
  input_control.py   # DirectX-friendly keyboard/mouse + smooth movement
  capture.py         # fast screen capture (mss)
  bobber.py          # bobber detection (cursor_scan + template)
  splash.py          # bite detection (sound + pixel)
```

---

## Notes on non-Windows

The `template` bobber strategy and `pixel` splash method are cross-platform, but
input injection into WoW and the most reliable detectors are built for Windows,
where WoW Classic runs. On macOS/Linux you'll get further with dry-run and the
cross-platform detectors, but sending input into the game is not guaranteed.
