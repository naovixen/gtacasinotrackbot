# insidetrack

An auto-bettor for GTA Online's **Inside Track** horse racing machine, driving
a PS5 over [chiaki-ng](https://github.com/streetpea/chiaki-ng) Remote Play.

It watches the betting board through screen capture, reads the six horses'
odds with OCR, picks one, walks the menus to place a maximum bet, waits out
the race, reads the winning lane off the result screen, logs the whole thing,
and starts again. Around 47 seconds a race, unattended — most of which is the
race itself.

> **This automates a live GTA Online money faucet. It violates Rockstar's
> Terms of Service, and people get banned and wiped for it.** Nothing in this
> repo changes that. Supervise it, and don't run it on an account you care
> about.

---

## Contents

- [Does it actually work?](#does-it-actually-work)
- [What you need](#what-you-need)
- [Setup](#setup)
- [Running it](#running-it)
- [Commands](#commands)
- [Quirks worth knowing before you start](#quirks-worth-knowing-before-you-start)
- [Configuration](#configuration)
- [When something goes wrong](#when-something-goes-wrong)
- [How it works](#how-it-works)

---

## Does it actually work?

The strategy is a published rule, replayed here over its author's own 547-race
log (`post-info/`). `python validate.py` reproduces every number below.

| strategy | ROI | $/race |
| --- | --- | --- |
| **pickorder** (the default) | **+50.6%** | **$4,917** |
| always the lowest odds | +42.2% | $4,223 |
| always track 3 | +29.6% | $2,962 |
| random lane | +12.6% | $1,261 |

The edge is real: every favourite wins more often than its price implies.
EVENS wins 56.2% of the time against a 50% break-even, 2/1 wins 45.0% against
33.3%, 4/1 wins 30.3% against 20.0%. Anything at 6/1 or longer is at or below
break-even and gets skipped.

Bootstrapping those 547 races 5,000× puts the rule's 95% interval at **+36.5%
to +65.5% ROI** — so expect a lot of variance. 547 races is not many, and an
hour well below the average is a normal outcome rather than a broken bot.

Throughput is the other half, and it is the half you control. The median cycle
over the 473 races in this repo's own `race_log.csv` is **47s, or ~76 races an
hour**, which puts the ROI interval at roughly **$270k–$480k/h**. `budget`
models the same figure from your timings and comes out optimistic (~85/h),
because it estimates the race wait rather than measuring it — the log is the
truth. Published claims of 103 races/h are faster than this gets.

The rule itself:

1. **Two horses at EVENS** → skip, minimum bet. The pair splits the win
   probability; backing one of them returned −25% over the 16 such races.
2. Otherwise back the first price present in **EVENS > 2/1 > 4/1 > 3/1 > 5/1**
   and max-bet it. (4/1 really does beat 3/1: close win rates, 5× vs 4× payout.)
3. Duplicates of the chosen price → lane 3, 2, 1, 6, 5, 4 in that order.
4. **Nothing better than 6/1** → skip, minimum bet.

There is a second strategy, `chart`, kept only for comparison. It looks better
in-sample (+57.4%) and is worse in reality (+38.2% cross-validated). Don't run
it for money.

---

## What you need

- **Windows.** Screen capture, the input backends and the window handling are
  all Win32.
- **Python 3.11+** (3.13 is what it is developed against — `tomllib` is stdlib
  from 3.11).
- **chiaki-ng**, streaming your PS5, with GTA Online open.
- Python packages:
  ```
  pip install easyocr opencv-python numpy mss pygetwindow pillow
  ```
  `easyocr` pulls in PyTorch and is the big one; the first run downloads its
  models. `tkinter` ships with Python on Windows and is used by the setup
  wizard.
- Optional, only for the fallback input modes:
  `vgamepad` (gamepad mode, needs [ViGEmBus](https://github.com/nefarius/ViGEmBus))
  and `pydirectinput` (keyboard mode).

---

## Setup

Where things sit on screen are pixel coordinates inside *your* chiaki-ng
window at *your* window size, so they cannot ship with the code. Nothing runs
until they are measured. One command does it:

```
python -m insidetrack setup
```

It tells you which game screen to be on and you press Enter; it grabs the
window and opens **that still picture in a window of its own**, where you
click the corners of each box. Roughly two minutes, and nothing is written
until the end.

Clicking happens on the still rather than the live game because **chiaki-ng
hides the mouse pointer while it is streaming** — over the one window that
matters there is nothing to aim with. The picker draws a crosshair, magnifies
the pixels under it at 8×, and previews the box you are drawing with its size,
then draws each finished box back on the picture and asks you to confirm it.

It asks for four things:

| put the game on… | and box… |
| --- | --- |
| the SINGLE EVENT board | lane 1's odds — both corners |
| the SINGLE EVENT board | lane 6's odds — top-left corner only |
| a horse selected, **stake run up to $10,000** | the stake ($ figure) — both corners |
| a race result | the winning horse's lane number — both corners |

Lanes 2–5 are spaced evenly between 1 and 6 (they are evenly stacked, and
measuring the two ends divides a spacing error by five instead of multiplying
it by five). If they land wrong, answer no and it takes all six corners by
hand.

The last two boxes can be skipped and added later by running `setup` again —
without the stake box, bets go on unverified; without the win-lane box, every
race is logged ungraded and `stats` has nothing to report.

### Draw the boxes for the *widest* text, not the text in front of you

This is the one thing that catches people. Each box is measured against
whatever the screen happens to show at that moment and then read forever
against everything else it can show.

- **Odds.** Lane 1's box sets the width for all six lanes. `EVENS` is five
  characters, `2/1` is three — a box drawn snugly around a `2/1` clips every
  `EVENS` from then on, and `EVENS` may not even be on the board while you are
  measuring. So take the right edge out into the empty space, stopping short of
  the horse's number diamond.
- **Stake.** The panel opens on `$100` and the bot runs it up to `$10,000` —
  four characters against seven — and `$10,000` is the *only* figure that box
  is ever read for. Run the stake up before measuring (Right onto the increase
  arrow, hold Cross), or leave room for three more digits and a comma.

Spare room inside a box is free: the reader crops to the ink before
recognising it, so an over-wide box reads identically — it still gets 6/6
lanes right with every box shifted up to 14px in any direction. Clipping is
not free. The wizard asks about both of these explicitly, with the box drawn.

### If you'd rather not use the wizard

```
python -m insidetrack setup --example   # drops insidetrack.toml to fill in
python -m insidetrack setup --manual    # same walkthrough, typed coordinates
python -m insidetrack setup --point     # hover the live screen, press F8
```

`insidetrack.example.toml` is the commented template. `--manual` saves each
screen as `setup-<name>-<step>.png` and asks you to type coordinates read off
it — `setup` falls back to this by itself if no window system is available.
`--point` is hover-and-press, which works but fights the hidden cursor.

### Then check it

```
python -m insidetrack probe    # calibrate.png + probe.png with the boxes drawn
python -m insidetrack read     # one board read, and what it would bet
python -m insidetrack keys     # confirm input reaches the PS5
python -m insidetrack tune     # ~1 min: do the timings hold up
```

`probe.png` draws red on the six odds, blue on the stake, yellow on the
winning lane. `keys` sends Right/Right/Left/Left to each candidate window in
turn so you can see which one the PS5 listens on — click away from chiaki-ng
first, so a pass only counts if it worked unfocused.

---

## Running it

Rehearse first. `--dry` decides and logs but sends no input at all:

```
python -m insidetrack run --dry
```

Open the SINGLE EVENT board by hand and let it read a few boards; check the
decisions look sensible. Then, for real:

```
python -m insidetrack run
```

Start it from the machine's start screen. Per race it prints the odds it read,
what it decided, the result, and a running session tally:

```
[21:04:12] odds=[1, 5, 13, 4, 26, 20] trusted=True -> EVENS in lane 1
  bet MAX on lane 1 (race #7)  cycle 46.9s (race 33.1s)  rate 76 races/h
  result: lane 1 (EVENS) won -- $20,000 back on $10,000
  session: 4/7 won, $58,000 back, net +$18,000 (+25.7% ROI) -> +$392,000/h
```

**ScrollLock pauses it**, at any time, from any window — it reads the toggle
state, so it works without focus. Turn it off to resume. Ctrl-C stops.

Every race is appended to `race_log.csv` — odds, choice, reason, stake,
winner, payout, timings — and `python -m insidetrack stats` reads it back:
what your own bets returned, broken down by price backed, by lane and by bet
size, plus the table of what actually *wins* over every board you've seen
whatever you bet on it. A few hundred graded races there are worth more than
the numbers at the top of this file.

---

## Commands

```
python -m insidetrack <command> [options]
```

| command | what it does |
| --- | --- |
| `setup` | measure this screen's boxes and write `insidetrack.toml` |
| `run` | place bets until stopped |
| `read` | one board read, and what the strategy would do with it |
| `result` | read the winning lane off a result screen |
| `probe` | save `calibrate.png` and `probe.png` to check the boxes |
| `keys` | find which window chiaki-ng takes input on |
| `tune` | check the timings against the real menu (~1 min, places no bets) |
| `budget` | model cycle time and $/hour from the timings |
| `stats` | what your own logged bets have returned |

| option | effect |
| --- | --- |
| `--screen NAME` | which `[screens.NAME]` block to use |
| `--config PATH` | a config file somewhere other than next to you |
| `--dry` | decide and log, send no input |
| `--strategy pickorder\|chart` | override the strategy for this run |
| `--input-mode postmessage\|gamepad\|keyboard` | override the input backend |
| `--debug-images` | save what the recogniser was actually given |

`python inside_track_bot.py <command>` is the same thing, kept as an entry
point. `python validate.py` reproduces the strategy analysis (~30s, or
`--quick`).

---

## Quirks worth knowing before you start

**The window has to be visible and unobscured.** Everything is measured off
real screen pixels. Another window sitting on top of chiaki-ng doesn't just
spoil the view, it breaks the capture — you will be OCR'ing whatever is in
front. Minimised is fatal for the same reason (the bot restores the window if
it finds it minimised, but won't fight you for it).

**It does not need focus, and that is the point.** In the default
`postmessage` mode, keystrokes are posted straight to the chiaki-ng window
handle, so they exist for that window only. You can keep using the PC while it
runs. Just don't drag anything over the stream.

**Re-run `setup` whenever the window moves or resizes.** Boxes measured at one
window size are wrong at another. chiaki-ng does not always restore the
geometry you left it at. If reads start failing, run `probe` and look at
`probe.png` before assuming the OCR broke.

**Don't touch the PS5's own controller while it runs.** A real input moves the
menu highlight out from under the bot, and it counts presses from where it
believes the cursor is.

**`result` only means anything on a result screen.** Run it while the board is
up and it will happily read a horse's saddle number, because the box happens
to sit there.

**chiaki-ng's keyboard mapping has to be live** for `postmessage` and
`keyboard` modes: Cross = Enter, Circle = Backspace, which are the defaults.

**Gamepad mode leaks into other programs.** A ViGEmBus virtual DualShock 4 is
a system-wide HID device. Steam in particular grabs it and, with a Desktop
layout active, retypes it into whatever window you have focused — this is the
"it's taking over my PC" effect, and it is why `postmessage` is the default.
If you genuinely need the pad:
[HidHide](https://github.com/nefarius/HidHide) (hide the pad from everything
except `chiaki-ng.exe`) is the real fix; turning off Steam's *PlayStation
Controller Support* or closing Steam works too. chiaki-ng also ignores
joystick events while unfocused unless you launch it with
`SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS=1`. The bot warns at startup if it sees
Steam running in gamepad mode.

**Keyboard mode types into whatever is focused.** Last resort only; you cannot
use the PC while it runs.

**A skip is still a bet.** When the board is bad (two EVENS, or nothing under
6/1), it places the $100 minimum rather than backing out — cheaper than the
navigation risk of leaving and re-entering.

**Unreadable results are left blank, not guessed.** If the winning lane won't
read, the race is logged without one and excluded from every ROI figure. A
missed read and a lost bet are not the same thing.

---

## Configuration

Everything lives in **`insidetrack.toml`**, next to you or next to the
package. It is not committed — it is specific to your window — and
`insidetrack.example.toml` is the template documenting every setting.

```toml
window_title = "chiaki"        # any window whose title contains this
default_screen = "main"        # used when --screen is not given
input_mode = "postmessage"     # postmessage | gamepad | keyboard
strategy = "pickorder"         # pickorder (validated) | chart
# post_target_index = 2        # from `insidetrack keys`; 0 = top-level

[screens.main]
odds = [
    [246, 371, 88, 48],   # lane 1
    [246, 496, 88, 48],   # lane 2
    ...
]
bet_amount = [1315, 480, 140, 75]
win_lane = [1405, 785, 80, 90]
```

Boxes are `[left, top, width, height]` in pixels **from the top-left of the
chiaki-ng window**, not of the screen. The corner form
`{ left = .., top = .., right = .., bottom = .. }` works anywhere too, and for
the odds you can give just `odds_lane1` and `odds_lane6` and let the four
between be spaced evenly.

Keep one `[screens.NAME]` block per layout — per monitor, per window size —
and pick between them with `--screen`.

A config is looked for in this order: `--config PATH`, then
`$INSIDETRACK_CONFIG`, then `insidetrack.toml` in the working directory, then
beside the package, then `~/.insidetrack.toml`.

There is also an optional `[timing]` block, which you should not need unless
navigation starts dropping presses:

```toml
[timing]
transition_gap = [0.4, 0.5]    # raise this FIRST if presses go missing
menu_tap_gap = [0.05, 0.06]    # then this
```

---

## When something goes wrong

**"No window matching 'chiaki'"** — chiaki-ng isn't running, is minimised, or
its title differs. Set `window_title` in the config.

**Odds read as `??`, or `trusted=False` every cycle** — the boxes have
drifted. Run `probe` and look at `probe.png`; if the red boxes aren't on the
odds, re-run `setup`. Check the window isn't covered.

**A price reads wrong in one lane only** — that box is probably clipping.
`EVENS` is the usual victim; see the widest-text note above.

**`win lane: UNREADABLE`** — run `result` on a real result screen, after a win
*and* after a loss. If it fails on both, the box is wrong; re-run `setup` and
measure it on a result screen. Races logged without a winner are dead weight:
they're excluded from `stats`, so the losses stop teaching you anything.

**Navigation desyncs — bets land on the wrong horse** — raise
`transition_gap` in `[timing]` first (the press right after a region change is
where drops actually happen), then `menu_tap_gap`. `tune` will tell you
whether a multi-lane walk is landing where it was aimed.

**Nothing reaches the PS5** — run `keys`. If a window other than `[1]` moved
the cursor, put its number in `post_target_index`. If none did, your chiaki-ng
build doesn't take posted key messages; switch `input_mode` to `gamepad` and
read the gamepad quirk above.

**"could not reach max, placing at $X"** — the bet-increase taps are being
eaten. The bot reads the amount back and tops up, so this is a warning rather
than a failure, but if it's constant, raise `bet_tap_gap`.

**The bot ends up in the open world** — it backed out too far. That is
unrecoverable by design (it only ever presses Circle once, confirmed), so put
it back on the machine's start screen and it will pick up.

---

## How it works

The package is layered so each piece can be tested without the game running.
`app.build()` assembles the object graph; nothing constructs its own
collaborators, so a test can hand `BoardReader` a fake screen and a scripted
recogniser.

| module | what it owns |
| --- | --- |
| `config` | profile / timing / settings shapes — data only |
| `userconfig` | `insidetrack.toml`: read, validated, written |
| `wizard` / `picker` | `setup`: the walkthrough, and the window you click on |
| `screen` | capture, and "has the picture stopped moving?" |
| `vision` | numpy preprocessing of a captured box |
| `ocr` | the recogniser, wrapped |
| `parsing` | text → odds, money, lane numbers |
| `board` | what the bot learns by looking |
| `backends` / `controller` | getting a keypress to the PS5, and making it land |
| `machine` | the betting machine as a sequence of screens |
| `strategy` | which horse, and what the race was worth |
| `racelog` / `stats` | the record, and reading it back |
| `loop` | the race cycle |
| `app` / `cli` / `diagnostics` / `tuning` | wiring and the commands |

A few decisions that are load-bearing:

**Nothing is timed by sleeping if it can be measured instead.** A press is
confirmed by watching whether the screen reacted, and the end of a race is
detected by the animation going still rather than by a fixed wait. The
stillness test adapts to how much motion an animation actually showed, because
a busy result screen never gets as quiet as an idle menu.

**All six lanes are read in one recognition pass.** They're stacked onto a
single canvas and matched back by row, which takes ~130ms against ~1040ms for
running the text detector once per lane. A lane whose text won't parse falls
back to the detector, so a hard read still costs what it always did. Only
lanes that came back doubtful are read a second time.

**Framing matters more than thresholds.** The recogniser scales whatever it's
given to a fixed height, so a box with the odds occupying a third of it
delivers tiny glyphs — that was the source of `13/1 → 19/1`. `prepare_text()`
crops to the ink and scales the *text*, which is why an over-wide box is
harmless.

**A bet is only placed from a screen we've proved we're on.** A trusted board
read is that proof. Anything unproven backs out one screen and restarts the
cycle, because the top of the loop is the thing that comes back in.

### Files

| file | what |
| --- | --- |
| `insidetrack/` | the bot |
| `inside_track_bot.py` | entry point, kept so the old commands still work |
| `insidetrack.example.toml` | config template — copy it, or run `setup` |
| `insidetrack.toml` | **your** boxes and settings (not committed) |
| `race_log.csv` | your own race-by-race record, appended forever |
| `validate.py` | reproduces the strategy analysis |
| `parse_races.py` | parses the published race logs |
| `post-info/` | the original posts and charts |
