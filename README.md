# WoW Classic Fishing Bot

An automated fisher for **World of Warcraft Classic**. It casts, spots the
bobber by **looking at the screen**, moves the cursor onto it **once**, lets it
**sit perfectly still** until the splash, then right-clicks to reel in — and
repeats. All timing and motion is randomized so it behaves like a real,
slightly distractible person, not a machine.

```
Cast  ->  spot bobber (no mouse sweeping)  ->  move onto it once  ->
          sit still & watch  ->  splash!  ->  react & right-click  ->  repeat
```

> ⚠️ Automating gameplay violates Blizzard's Terms of Service and can get your
> account banned. You've accepted that risk — this note is just so it's stated
> plainly. Use an account you're willing to lose.

---

## The 3-step quick start (Windows)

```bash
# 1. install once
pip install -r requirements.txt

# 2. cast in-game, then CHECK that it sees your bobber (this sends NO input):
python preview.py
#    -> open detection_preview.png; you should see a green crosshair on the bobber

# 3. fish:
python run.py
#    -> it starts PAUSED. Alt-tab into WoW and press F9 to begin. F10 to stop.
```

That's the whole thing. If step 2 already puts the crosshair on your bobber,
step 3 will just work. If it doesn't, see **"If it can't find the bobber"** below.

Before you start, in WoW:
- Display mode = **Windowed (Fullscreen)** (not exclusive fullscreen).
- Put **Fishing** (or a `/cast Fishing` macro) on a hotbar key; set `keys.cast`
  in `config.yaml` to match (default `8`).
- Turn on **Auto Loot** (Interface → Controls) for clean pickups.
- Equip your pole, stand still, face the water.

---

## How it finds the bobber (no robotic mouse sweeping)

The bobber is located purely from screen pixels — **the mouse doesn't move while
searching**. The default `vision` strategy keys on the standard Classic bobber's
signature: a **red feather sitting just above a steel-blue band**. That red-over-
blue pairing basically never occurs by chance in the water, so it's a reliable,
low-false-positive fingerprint — and it needs no setup or template image.

Once found, the cursor glides to the bobber **one time** along a natural curved
path, then holds still and watches for the splash. When the bobber dips, a short
human reaction delay passes and it right-clicks in place. That's exactly the
flow a person uses.

---

## Human-like behavior (anti-detection)

- **Curved, eased mouse motion** with occasional overshoot-and-correct — never a
  straight teleport.
- **The cursor sits still on the bobber** while waiting — no jitter, no sweeping.
- **Gaussian-jittered timing** for casts, reactions, and waits.
- **Human reaction delay** (default 180–520 ms) between splash and click.
- **Occasional distractions** — briefly drifts the mouse away and pauses.
- **Breaks** every ~55–120 casts (25–140 s), like stepping away.
- **Rare fumbles** — a mistimed cast now and then.
- **Session limit** — auto-stops after a set number of minutes.
- **DirectX-correct input** via `pydirectinput`, which WoW actually registers.

All tunable in `config.yaml` under `human:`.

---

## If it can't find the bobber

Run `python preview.py --loop` and watch `detection_preview.png` update. Then:

1. **Wrong area?** The watched `region` may not cover where your bobber lands.
   Run `python calibrate.py` and draw a tight box around your splash zone. A
   tighter box is faster and avoids false positives.
2. **Different fishing spot / camera?** The bobber moved. Re-run `calibrate.py`
   for the new spot.
3. **Still missing it?** Capture your exact bobber as a template:
   `python calibrate.py` → answer "yes" to the bobber capture step. The bot will
   then also multi-scale template-match your real bobber image.
4. **Send me `detection_preview.png`** — it shows exactly what the bot sees and
   makes it easy to tune.

---

## Splash (bite) detection

Default is **`pixel`**: it watches a small box around the bobber and fires when
the splash foam changes enough pixels. No extra setup.

Prefer detecting the bite by **sound** (very reliable, mirrors how you'd hear it)?
Set `splash.method: sound` in `config.yaml` (Windows; needs `PyAudioWPatch`,
installed by `requirements.txt`).

---

## Controls

| Key | Action |
|-----|--------|
| **F9** | Pause / resume (bot starts paused) |
| **F10** | Quit |
| **Ctrl+C** in the terminal | Force quit |

---

## Testing without touching the game

- `python preview.py` — see detection only, sends nothing.
- `python run.py --dry-run` — runs the full loop and logs what it *would* do, but
  never presses keys or clicks.

---

## Config cheatsheet (`config.yaml`)

```yaml
keys:
  cast: "8"                    # your Fishing hotbar key
region: [335, 175, 1115, 705]  # the big "bobber can land anywhere" box (1080p)
ignore_zones: []               # optional rects to blank out (e.g. a nameplate)
bobber:
  strategy: "vision"           # red+blue signature; no template needed
splash:
  method: "pixel"              # or "sound"
human:
  reaction_ms: [180, 520]
  break_every_casts: [55, 120]
  max_session_minutes: 150
control:
  start_paused: true
  dry_run: false
```

---

## Project layout

```
run.py           # main entry point (F9 start / F10 stop)
preview.py       # SAFE detection check -> writes detection_preview.png
calibrate.py     # set the fishing region (and optionally capture your bobber)
config.yaml      # all settings, commented
requirements.txt
fishbot/
  bot.py           # main loop + controls, breaks, distractions, session cap
  bobber.py        # vision detection: red+blue signature, template, blob
  splash.py        # bite detection (pixel + sound)
  input_control.py # DirectX-friendly input + smooth curved movement
  capture.py       # fast screen capture (mss)
  humanize.py      # timing jitter + Bezier mouse paths
  config.py        # typed config with defaults
```

---

## Non-Windows note

The `vision`/`template` bobber detection and `pixel` splash method are
cross-platform, but reliably injecting input into WoW (and sound-based splash
detection) are built for Windows, where WoW Classic runs. Elsewhere, use
`--dry-run` and `preview.py` to exercise detection.
