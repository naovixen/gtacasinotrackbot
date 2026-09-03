# Inside Track bot — validation results and the input-isolation fix

Two things were asked for: check the strategy against the better data, and
stop the bot from taking over the PC. Both are done. This file is the
reasoning; the code changes are in `inside_track_bot.py`, and every number
below is reproducible with `python validate.py`.

---

## Part 1 — Strategy validation

### What I did

`post-info/SecondPost.md` contains his full 547-race log (`2xw,8,5w,20,1,2.`
= six tracks, `x` = his bet, `w` = winner). `parse_races.py` parses it;
`validate.py` replays strategies over it using his accounting — stake 100 per
appearance, a win on an n/1 horse returns (n+1)×, only the slot marked `w`
pays.

Sanity check that the parse is right: my per-horse ROI comes out at
1=+12% 2=+35% 3=+7% 4=+52% 5=+22%, against his published
1=+14% 2=+36% 3=+4% 4=+51% 5=+18%. Same numbers within the 512-vs-547 race
difference, so the accounting matches his.

### The headline: his claim checks out, at the bottom of the band

| strategy | ROI | $/race | $/h at 103 races/h |
|---|---|---|---|
| his stated rule (now the default) | **+50.6%** | $4,917 | **$506k** |
| always the lowest odds | +42.2% | $4,223 | $434k |
| always track 3 | +29.6% | $2,962 | $305k |
| random lane | +12.6% | $1,261 | $130k |

The edge is real and large: **every favourite wins more often than its odds
imply.** EVENS wins 56.2% of the time against a 50% break-even, 2/1 wins
45.0% against 33.3%, 4/1 wins 30.3% against 20.0%. Horses at 6/1 and longer
are at or below break-even — correctly ignored.

Bootstrapping the 547 races 5,000×, the pick-order rule's 95% interval is
**+36.5% to +65.5% ROI**, i.e. **$376k–$674k/h**. So "500–800k/h" is a fair
headline but optimistic at the top; 547 races is not many, and an hour well
below 500k is a normal outcome, not a broken bot.

### The important finding: our chart implementation was overfit

The bot was using the per-(track, horse) ROI tables from the *first* post
(283/153/61 races). Those score **+57%** on the full log and look like an
upgrade. They are not:

| test | chart | pickorder |
|---|---|---|
| in-sample, all 547 races | +57.4% | +50.6% |
| 132 races recorded *after* the charts were published | +53.1% | **+69.0%** |
| 5-fold CV, charts refitted per split (20 shuffles) | +38.2% | **+50.6%** |

Each chart cell rests on 7–40 appearances and 1–20 wins. Picking the `max()`
of six such cells reliably selects whichever one got lucky, so the in-sample
ROI is an artefact of the selection, not an edge. Shrinking the cells toward
the horse-level average doesn't rescue it either (I tested k=20/60/150; all
land at +36–37% out-of-sample).

**Change: `STRATEGY` now defaults to `"pickorder"`.** Chart mode is still
there for comparison and its tables have been recomputed from the full
547-race log, but don't run it for money.

### The pick order itself is correct

Marginal per-horse ROI is misleading — it says 4/1 is the best horse overall
(+52%) and EVENS is nearly the worst (+12%), which would suggest betting 4/1
first. That's a selection effect: horse 4's average is inflated by the races
where no favourite is present. The clean test is head-to-head, restricted to
races containing **both** horses so the comparison is on identical races:

```
 1 vs 2   n=38     +0.0%   -21.1%   -> 1
 1 vs 3   n=51    +37.3%   -60.8%   -> 1
 1 vs 4   n=37     +2.7%   -18.9%   -> 1
 1 vs 5   n=59    +18.6%   +11.9%   -> 1
 2 vs 3   n=62    +59.7%    +9.7%   -> 2
 2 vs 4   n=37    +54.1%    -5.4%   -> 2
 2 vs 5   n=40    +57.5%    +5.0%   -> 2
 3 vs 4   n=38    +15.8%  +110.5%   -> 4
 3 vs 5   n=52    +30.8%   +15.4%   -> 3
 4 vs 5   n=40   +100.0%   +35.0%   -> 4
```

That's a consistent total order: **1 > 2 > 4 > 3 > 5**, exactly his. 4/1
beating 3/1 is genuine — their win rates are close (30.3% vs 26.7%) while
4/1 pays 5× against 4×. Inside the 185 one-EVENS races, betting the EVENS
returns +16.8% while betting the 2/1 instead returns −21.1%: always take the
shortest price.

The two-EVENS skip is also right — betting one of a pair returns −25% ROI
over the 16 such races, because the two split the win probability.

The lane tiebreak (3,2,1,6,5,4) only fires in 14% of races and is worth about
one ROI point across all 720 orderings. Left as he specified it.

### Throughput is what actually decides whether you hit 500k

Strategy gives $4,917 per race. Everything after that is race rate:

| races/h | s/race | $/h |
|---|---|---|
| 60 | 60.0 | $295k |
| 75 | 48.0 | $369k |
| 90 | 40.0 | $443k |
| **103** | **35.0** | **$506k** ← his pace |

The old timing constants could not get there. Modelling them
(`python inside_track_bot.py budget`):

```
 safe: nav  7.0s  betspam 4.4s  ocr 3.1s  race 34.0s  = 48.5s/race ->  74 races/h -> $365k/h
 fast: nav  2.2s  betspam 1.4s  ocr 1.6s  race 31.5s  = 36.7s/race ->  98 races/h -> $482k/h
```

Roughly 14s per race was overhead: 0.30–0.45s between every navigation press
plus a 20% chance of an extra 0–0.5s "hesitation", a 0.07–0.12s hold on each
of the 28 bet-increase taps, a 1.0s OCR settle, and two full six-lane board
reads every race.

**Changes:**
- `TIMING_PROFILE` with `safe` (the old values) and `fast`, defaulting to `fast`.
- The second board read is now only spent when the first read is incomplete
  or below the confidence bar, instead of every race.
- The run loop prints the achieved cycle time, races/hour and projected $/h
  after each race, so you can tune against reality instead of the model.
- `python inside_track_bot.py budget` shows the model for both profiles.

`race_wait` (31.5s) is the floor and the one value I could not measure
without the game in front of me. Lower it a second at a time until
`bad/untrusted read` starts showing up in the log, then add one back.

---

## Part 2 — Why it takes over your PC, and the fix

### What's actually happening

A ViGEmBus virtual DualShock 4 is a **system-wide HID device**. It isn't
addressed to chiaki-ng; it's a controller plugged into Windows, and every
process that reads controllers sees every button press.

The specific culprit is almost certainly **Steam**. If Steam is running with
PlayStation controller support on, it captures the virtual DS4 and applies
its *Desktop* configuration — which by default remaps a controller into
mouse movement, clicks and keystrokes aimed at **whatever window has
focus**. So the moment you click into another program, Steam faithfully
retypes the bot's D-pad and X presses into it. chiaki-ng's own docs call out
Steam Input interference for exactly this reason. Anything else that reads
gamepads (Game Bar, a launcher, a focused game, a browser page using the
Gamepad API) can do the same.

Making the pad "background" doesn't help — the problem isn't that chiaki-ng
misses input, it's that everything else *receives* it.

### Fix A — `INPUT_MODE = "postmessage"` (now the default)

Instead of synthesising a system-wide input event, post the key messages
directly to chiaki-ng's window handle:

```python
_user32.PostMessageW(hwnd, WM_KEYDOWN, vk, lparam)
```

That message is delivered to one HWND's message queue. No other process can
observe it, the window does not need focus, and there is nothing for Steam
to intercept. chiaki-ng is a Qt app and Qt translates `WM_KEYDOWN`/`WM_KEYUP`
into key events for the window that received them, which is why this works
unfocused. (The `lParam` carries the scan code and the extended-key bit, so
the arrows are distinguishable from the numpad — Qt reads that.)

**This is verified working on your machine.** With chiaki-ng sitting on the
Inside Track results screen and **PyCharm holding the foreground**, I posted
a Cross (Enter) to its HWND. The "BET AGAIN" button fired and the game
returned to the machine's start screen — a 100× jump over the video stream's
own frame-to-frame noise (43.07 vs a 0.42 idle baseline), while
`GetForegroundWindow()` stayed on PyCharm before and after. Background input,
correct window, no focus theft.

Your chiaki-ng is a single top-level Qt 6.9.1 window (`Qt691QWindowIcon`)
with no child windows, so `POST_TARGET_INDEX = None` is right and `keytest`
will only ever list one target.

**Re-test it if anything changes:**

```
python inside_track_bot.py keytest
```

It lists the chiaki-ng top-level window and its child windows, then sends
Right, Right, Left, Left to each in turn. **Click on another window first**,
so a pass only counts if it worked while unfocused. Watch the PS5 screen:

- Index `[1]` moved the cursor → done, leave `POST_TARGET_INDEX = None`.
- A child index moved it → set `POST_TARGET_INDEX` to that number.
- Nothing moved → your chiaki-ng build doesn't take posted key messages;
  go to Fix B.

Note this drives chiaki-ng's **keyboard** mapping (Cross = Enter, Circle =
Backspace by default), so those bindings need to be live in chiaki-ng.

### Fix B — gamepad mode done properly

If you need the virtual pad, the only airtight answer is to stop other
processes from seeing the device at all:

1. **[HidHide](https://github.com/nefarius/HidHide)** — same author as
   ViGEmBus. Install it, add the ViGEm virtual DualShock 4 to the hidden
   device list, and whitelist **only** `chiaki-ng.exe`. Every other process
   on the machine, Steam included, then cannot enumerate the pad. This is
   the real fix and it is what the tool exists for.
2. **Steam** — if you'd rather not install a driver: Settings → Controller →
   turn off *PlayStation Controller Support*, and make sure Steam isn't
   running with a Desktop layout active. Closing Steam entirely also works.
3. **Let chiaki-ng read the pad unfocused** — chiaki-ng uses SDL, and SDL
   ignores joystick events while unfocused unless told otherwise. Launch it
   with the hint set:
   ```powershell
   $env:SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS = "1"
   & "C:\Program Files\chiaki-ng\chiaki-ng.exe"
   ```

The bot now warns at startup if you're in gamepad mode with Steam running.

### Fix C — what changed regardless of mode

- `focus_window()` → `ensure_window()`. It restores the window if minimised
  (screen capture needs real pixels) but **never calls `activate()`** unless
  you're deliberately in `keyboard` mode. The old code called it every loop.
- **ScrollLock pauses the bot**, from any window, without focus — read via
  `GetKeyState`, checked at the top of each race. Panic button that doesn't
  require finding the console.
- A preflight banner prints the input mode, the target HWND, and the Steam
  warning before the first bet.

`keyboard` mode is still there but it is the one mode that inherently types
into the focused window. Don't use it if you want the PC.

---

## Files

| file | what |
|---|---|
| `inside_track_bot.py` | the bot |
| `inside_track_bot.py.bak` | the previous version, for diffing |
| `parse_races.py` | parses the Reddit race logs |
| `validate.py` | reproduces every number in this document |
| `post-info/` | his posts and charts |

```
python validate.py                       # full report (~30s)
python validate.py --quick               # skip bootstrap + cross-validation
python inside_track_bot.py budget        # cycle-time / $-per-hour model
python inside_track_bot.py keytest       # find the input target window
```

---

## One thing you need to check before running

**Your calibration is probably stale.** chiaki-ng's saved geometry in the
registry is `3440x1417`, but the window is currently **2904x1679** at
`(-3218, -154)`. Both `PROFILES` entries were measured at some other size, so
the OCR boxes will not be sitting on the odds any more. It was also partly
covered by a Paint window while I was looking, which breaks screen capture
outright — the window has to be unobscured, even though it no longer needs
focus.

Run `probe` and check `probe.png` before betting real money; recalibrate if
the red boxes have drifted.

## Suggested first run

1. `python inside_track_bot.py keytest` — confirm postmessage drives the PS5
   menu while another window has focus. (Already verified once above.)
2. `python inside_track_bot.py probe` — confirm the OCR boxes still sit on
   the odds for your profile. **Do this one — see above.**
3. Set `DRY_RUN = True`, `TIMING_PROFILE = "safe"`, run a few minutes and
   check the decisions in the log read sensibly.
4. `DRY_RUN = False`, still on `safe`, watch that navigation never desyncs.
5. Switch to `fast` and watch the printed races/hour. Tune `race_wait` down
   until reads start failing, then back off one second.

Standing caveat: this is automating a live GTA Online money faucet. Rockstar
bans for it. Nothing here changes that.
