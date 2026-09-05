# Measuring the boxes

[← back to the README](../README.md)

Where things sit on screen are pixel coordinates inside *your* chiaki-ng
window at *your* window size, so they cannot ship with the code. Nothing runs
until they are measured, and `python -m insidetrack setup` measures them.

## What the wizard asks for

It tells you which game screen to be on and you press Enter; it grabs the
window and opens **that still picture in a window of its own**, where you
click the corners of each box. Roughly two minutes, and nothing is written
until the end.

(The clicking window is tkinter, which ships with Python on Windows. If it
isn't available, `setup` falls back to typed coordinates on its own.)

| put the game on… | and box… |
| --- | --- |
| the SINGLE EVENT board | lane 1's odds — both corners |
| the SINGLE EVENT board | lane 6's odds — top-left corner only |
| a horse selected, **stake run up to $10,000** | the stake ($ figure) — both corners |
| a race result | the winning horse's lane number — both corners |
| the same race result | the RESULTS title panel — both corners |

Lanes 2–5 are spaced evenly between 1 and 6 (they are evenly stacked, and
measuring the two ends divides a spacing error by five instead of multiplying
it by five). If they land wrong, answer no and it takes all six corners by
hand.

The last two screens' boxes can be skipped and added later by running `setup`
again — without the stake box, bets go on unverified; without the win-lane
box, every race is logged ungraded and `stats` has nothing to report; without
the RESULTS box, every race pays a few seconds waiting to be sure it is over
(see [Knowing the race is over](race-detection.md)).

## Why you click on a still picture

Clicking happens on the still rather than the live game because **chiaki-ng
hides the mouse pointer while it is streaming** — over the one window that
matters there is nothing to aim with. The picker draws a crosshair, magnifies
the pixels under it at 8×, and previews the box you are drawing with its size,
then draws each finished box back on the picture and asks you to confirm it.

## Draw the boxes for the *widest* text, not the text in front of you

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

## If you'd rather not use the wizard

```
python -m insidetrack setup --example   # drops insidetrack.toml to fill in
python -m insidetrack setup --manual    # same walkthrough, typed coordinates
python -m insidetrack setup --point     # hover the live screen, press F8
```

`insidetrack.example.toml` is the commented template. `--manual` saves each
screen as `out/setup-<name>-<step>.png` and asks you to type coordinates read
off it — `setup` falls back to this by itself if no window system is
available. `--point` is hover-and-press, which works but fights the hidden
cursor.

## Checking the result

```
python -m insidetrack probe    # out/calibrate.png + out/probe.png, boxes drawn
python -m insidetrack read     # one board read, and what it would bet
python -m insidetrack keys     # confirm input reaches the PS5
python -m insidetrack tune     # ~1 min: do the timings hold up
```

`out/probe.png` draws red on the six odds, blue on the stake, yellow on the
winning lane. `keys` sends Right/Right/Left/Left to each candidate window in
turn so you can see which one the PS5 listens on — click away from chiaki-ng
first, so a pass only counts if it worked unfocused.

**Re-run `setup` whenever the window moves or resizes.** Boxes measured at one
window size are wrong at another, and chiaki-ng does not always restore the
geometry you left it at.
