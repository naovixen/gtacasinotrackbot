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
- `TIMING_PROFILE` with `safe` (the old values), `steady` (default) and
  `fast`. *(Superseded — see "The profiles are gone" below: there is now one
  set of numbers, no profile to choose.)*
- The second board read is now only spent when the first read is incomplete
  or below the confidence bar, instead of every race.
- The run loop prints the achieved cycle time, races/hour and projected $/h
  after each race, so you can tune against reality instead of the model.
- `python inside_track_bot.py budget` models the cycle time for those
  numbers in races/hour and $/hour.

### Where presses were actually getting lost

My first cut at this was wrong. I assumed short key holds were being dropped
because chiaki samples controller state periodically, so I set the `fast`
profile to a 30–45ms hold. That caused dropped navigation, but not for the
reason I gave — and the fix was in the wrong place.

Measured on your connection with `tune`, driving the real lane list:

```
  20ms hold: 6/6 registered      120ms cycle: [5,5,5,5] lanes    ok
  30ms hold: 6/6 registered      150ms cycle: [5,5,5,5] lanes    ok
 220ms hold: 6/6 registered      600ms cycle: [5,5,5,5] lanes    ok
```

A 5-lane walk landed correctly at **every** combination tried, down to a 20ms
hold and a 120ms press-to-press cycle. Hold length is irrelevant here, and
repeated presses inside one region are robust. Round-trip latency
(post → PS5 → stream → screen) measured a stable **282ms**.

What actually drops is the press that **crosses a boundary**, while the UI is
still animating:

- nothing selected → `Left` brings the cursor in at lane 6
- `Cross` selects the horse and the right-hand bet panel redraws
- `Right` jumps from the horse column into that bet column

Those three now use `tap_edge()` and a separate `transition_gap` (0.46–0.60s),
while the lane walk between them stays on the quick `menu_tap_gap` (0.13–0.17s).
Slowing *every* press to cover three of them is what made the original profile
take 48s a race.

The other regression was mine: the `fast` bet spam ran at a 30–50ms cycle,
three times faster than anything that has been shown to work. It is now
~0.11s per tap, and `verify_max_amount()` reads the amount back off the screen
either way.

### The profiles are gone; there is one set of numbers

`safe` / `steady` / `fast` were three guesses, and choosing between them was a
coin toss made once and never revisited. `TIMING`, near the top of the file, is
now the only set.

| | safe (old) | fast (old) | now |
|---|---|---|---|
| `menu_tap_gap` | 0.30–0.45s | 0.11–0.15s | **0.065–0.085s** |
| `transition_gap` | 0.60–0.80s | 0.38–0.52s | **0.31–0.40s** |
| `key_hold` | 0.07–0.12s | 0.045–0.065s | **0.050–0.070s** |
| `spam_hold` + `bet_tap_gap` | ~0.15s/tap | ~0.095s/tap | **~0.086s/tap** |
| `ocr_settle` | 1.0s | 0.35s | **0.42s** |

That models at **39.8s a race, 90 races/h, ~$445k/h** (`budget`), against 48.5s
and 74 races/h on the old `safe` numbers — within touching distance of his
claimed 103.

They are trimmed past what has been measured, deliberately, and the file records
where each one stands:

- **Lane walk: inside the evidence.** `key_hold` + `menu_tap_gap` is ~135ms
  press-to-press, and a 5-lane walk landed 5/5 at a 120ms cycle.
- **Crossing: thin.** The press goes in ~355ms after the one that started the
  animation, against a 282ms measured round trip. Three of the eight crossings
  are confirmed against the picture and retry; the other five are not, and a
  swallowed press there desyncs the rest of the sequence.
- **Bet spam: just under it.** ~86ms a tap, against the ~0.11s shown to reach
  $10,000 and the 30–50ms found to drop taps — much nearer the first than the
  second. It also fails cheaply: `verify_max_amount()` reads the amount back off
  the screen and tops it up, so the cost is seconds rather than a wrong stake.

The log says which one gave way first: `(cross did not register, retry 2/3)` for
a crossing, `(amount $X: some taps eaten)` for the spam. Give ground in that
order — `transition_gap`, then `menu_tap_gap`.

`python inside_track_bot.py tune` still checks them against the real lane list
in about a minute, and if navigation desyncs the knob to raise is
`transition_gap` first, then `menu_tap_gap`.

#### Why they are not measured automatically

The obvious next step was a probe that ramps each part of the cycle until it
breaks and keeps the last speed that held — separately per part, since a lane
walk survives gaps less than half of what a region crossing needs. It was
built, it worked against a simulated menu, and it does not work here. It has to
score each trial by looking at the screen, and on this stream the frame-to-frame
difference while *nothing is happening* measured **larger than the difference
between one highlighted lane and the next** (noise floor 98 against a
separation of 60). Averaged over the window, a highlight moving between two
adjacent buttons in the bet row is an order of magnitude below the noise it is
being compared against; measured tile by tile to get around that, the noise
comes up with it.

There is nothing to measure against, so the numbers above are chosen inside the
bands `tune` has already validated rather than derived. Two things worth keeping
from the attempt:

- **Never count presses backwards out of the menu.** The probe pressed Circle
  three times to reach the machine's start screen from the board. That is one
  press too many — the second Circle leaves the terminal, and every press after
  it goes into the game world. `back_out()` had the same bug, so `recover()`
  could have walked out of the machine mid-session; it now stops as soon as it
  recognises the start screen, which `enter_single_event()` remembers on the way
  in.
- **A bet-spam check that does not rely on pixels.** Before spamming X, confirm
  the button by *using* it: one press, and the amount has to go up by the right
  step. Being wrong about which button that is would be twenty real bets.

### The Place Bet hang

First version of the above got one boundary wrong and `fast` would sit
hovering on Place Bet. `tap_edge()` puts its long gap *after* a press, which
is right when that press is the one starting an animation — but the Cross on
Place Bet needs the room *before* it, because the preceding `Down` is what
moves the highlight into the button row. That Down was a plain tap, so the
Cross arrived ~110ms later and was swallowed. It is now `tap_edge("down")`.

Guessing every boundary correctly is fragile, so the presses that change the
whole screen no longer rely on it. `tap_confirm()` presses, watches for the
picture to actually change, and presses again if it did not — up to three
times. It is used for entering the single-event screen, placing the bet, and
BET AGAIN. `place_bet()` now returns whether the bet went on; if it did not,
the loop recovers rather than counting a race that never ran.

The threshold for "the screen reacted" is measured once against your idle
stream (the menus animate, so it isn't zero) and capped. On this setup it
came out at 2.19, against ~43 for a real screen change — a 20× margin.

### The race wait is no longer a guess

`race_wait` is gone. `wait_for_race_end()` sleeps a minimum, then watches the
picture and continues once the animation stops moving — measured against how
much motion *that* race actually showed, with a hard cap. So a slow race is
waited out and a quick one isn't sat through, and the log prints the real
race duration each cycle.

### It gets back to BET AGAIN (the `fast` stall)

On `fast` the loop could finish a race and never restart: the result screen
came up, and the bot sat on it instead of pressing BET AGAIN. Three things
lined up, all of them still latent on the slower profiles:

1. **`tap_confirm()` confirmed presses it had not made.** It pressed, then
   watched for the picture to change. On the *result* screen the picture is
   changing anyway — the payout counts up, horses mill around — so the very
   first frame after the press differed from the baseline and the confirm
   passed with the Cross swallowed. It now waits for the picture to be
   **still** before it presses, so the change it measures is one it caused,
   and re-checks after the transition gap that the change stuck rather than
   being a one-frame flicker.

2. **`wait_for_race_end()` could return mid-race.** "Settled" was purely
   relative — below 25% of the motion that race had shown — so a camera cut
   or a quiet straight cleared it after three samples (~1s). It now needs
   five consecutive quiet samples (~1.8s) *and* absolute quiet measured
   against the same idle-noise threshold the confirms use. `fast` also had
   `race_wait_max` trimmed to 42s, which on a long race simply walked off the
   still-running screen; it is back to 46s. That cap is a safety net, not a
   speed knob — only a long race ever reaches it.

3. **Nothing checked whether it worked.** `return_to_start()` already
   returned a status and `run()` threw it away. Now: the result screen is
   given up to 10s to settle, the Cross gets four confirmed attempts (with no
   extra `Down`s, which would walk the highlight *off* BET AGAIN), and if it
   still fails the loop backs out with Circle so the next cycle starts from
   the machine start screen instead of somewhere unknown.

The cycle cost of the settle waits is ~0.9s a race, which `budget` now
accounts for.

### It no longer bets blind when it's lost

A trusted board read is also the proof that you're on the betting screen. If
two reads in a row fail, `recover()` backs out to the machine start screen and
comes in again, instead of the old behaviour of pressing on and placing a
"min-bet skip" from an unknown screen — which is how one dropped press turned
into a bet on the wrong horse.

`python inside_track_bot.py tune` is now a ~1 minute check that the timings
walk lanes correctly and that the post-transition press survives, rather than
the long sweep it started as.

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

## Part 3 — Our own record (`race_log.csv`)

Every ROI figure in Part 1 is fitted to **his** 547 races. The bot now keeps
its own book so we can stop taking his word for it.

### How a race gets graded

One box on the result screen, read after `wait_for_race_end()` and **before**
anything is pressed — once BET AGAIN goes in, it's gone:

```python
"win_lane_region": (1405, 785, 80, 90),   # 4k profile
```

The number of the horse that won is the entire result. It grades *every*
race, including the ~50% we lose, which the payout never could — and combined
with the whole board in `odds1…odds6`, a losing race stops being a blank and
becomes a full observation: which price won, out of which six were on offer.

**The amount-won box isn't read at all.** Inside Track pays `(odds + 1) ×
stake`, so once we know the board and the winning lane the payout is
arithmetic, not something to OCR: `grade()` computes it. That's one fewer OCR
pass per race and one fewer box to keep calibrated.

The read waits for two consecutive agreeing OCR passes, so it isn't caught
mid-animation, and it's a cheap one — a single digit, allowlist `123456`.
Text it can't resolve (nothing, or more than one digit) is logged **blank**,
never as a loss: a missed read and a losing bet are very different things
once you start fitting numbers to this.

### What gets written

One row per placed bet, appended to `race_log.csv` next to the script. Rows
are only ever appended and each run stamps its own `run_id`, so a new session
never overwrites an old one. If the columns ever change, the old file is
renamed to `race_log.<run_id>.old.csv` rather than being appended to with a
mismatched header.

| column | what |
|---|---|
| `run_id`, `ts` | which session, and when |
| `profile`, `strategy`, `timing`, `dry` | the conditions the bet was placed under |
| `odds1`…`odds6` | the whole board, not just the horse we backed |
| `lane`, `horse`, `max_bet`, `reason` | what we bet and why `decide()` said so |
| `stake` | read back off the screen, so it's what was really bet, not what was intended |
| `win_lane`, `win_odds` | which lane won, and the price that horse was at |
| `won`, `payout`, `profit` | did we win, and the money — computed from the odds and the winning lane |
| `trusted`, `race_s`, `cycle_s`, `settled` | OCR confidence and timing, for debugging bad rows |

Keeping the full board matters: it's what lets us ask later whether backing
4/1 over 3/1 was right *on the boards we actually saw*, rather than re-testing
the pick order on the same data it came from.

### Reading it back

```
python inside_track_bot.py stats
```

Breaks the log down by horse backed (with the break-even win rate for each
price), by lane, and by bet size, plus the last 50 races so drift shows up.

Then the table the whole thing is for — **what actually wins**, over every
race, whatever we bet:

```
    price    appeared   won  win rate  break-even  flat ROI
    EVENS          72    17     23.6%       50.0%    -52.8%
    2/1           139    31     22.3%       33.3%    -33.1%
    4/1           138    26     18.8%       20.0%     -5.8%
```

That is the same measurement `validate.py` runs over his 547 races — flat-bet
ROI for backing a price every time it appears — computed on boards we read
ourselves. `PICK_ORDER` is currently `[1, 2, 4, 3, 5]` on his numbers; this
column is what eventually replaces it.

### Calibrating the box

`probe` draws the win-lane box in yellow alongside the red odds boxes, so run
it on a **result** screen as well as on the betting board:

```
python inside_track_bot.py probe 4k
python inside_track_bot.py result 4k
```

`result` reads the result screen once and prints the lane it got. Do it on a
winning result screen and on a losing one — if the digit doesn't come through
on both, races land in the log ungraded and everything downstream is built on
a biased sample.

The `main` profile has no `win_lane_region` measured yet, so runs on that
screen log races without results and say so at startup.

---

## Files

| file | what |
|---|---|
| `inside_track_bot.py` | the bot |
| `race_log.csv` | our own race-by-race record, appended forever (Part 3) |
| `inside_track_bot.py.bak` | the previous version, for diffing |
| `parse_races.py` | parses the Reddit race logs |
| `validate.py` | reproduces every number in this document |
| `post-info/` | his posts and charts |

```
python validate.py                       # full report (~30s)
python validate.py --quick               # skip bootstrap + cross-validation
python inside_track_bot.py budget        # cycle-time / $-per-hour model
python inside_track_bot.py keytest       # find the input target window
python inside_track_bot.py tune          # ~1 min timing check
python inside_track_bot.py probe 4k      # probe.png with the OCR boxes drawn on
python inside_track_bot.py result 4k     # check the winning-lane OCR box
python inside_track_bot.py stats         # what OUR bets have returned
```

Any command takes these in any order — no editing the file:

| argument | effect |
|---|---|
| `main` / `4k` | which screen profile's coordinates to use |
| `--dry` | decide and log, send no input |
| `--chart` / `--pickorder` | override the strategy for this run |

So `python inside_track_bot.py run 4k`, or
`python inside_track_bot.py run 4k --dry` to rehearse it first. The preflight
banner prints the screen profile, the timings and the strategy before the first
bet.

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
2. `python inside_track_bot.py probe 4k` — confirm the OCR boxes still sit
   on the odds for your profile. **Do this one — see above.**
3. `python inside_track_bot.py tune 4k` — a minute, on the SINGLE EVENT board.
   Confirms the timings walk lanes without dropping presses. Focus does not
   matter — `postmessage` posts to the chiaki-ng window handle — but the window
   must stay visible and unobscured, because everything is scored by reading
   pixels.
4. Set `DRY_RUN = True`, run a few minutes and check the decisions in the log
   read sensibly.
5. `DRY_RUN = False`, watch that navigation never desyncs. If it does, raise
   `transition_gap` in `TIMING` first, then `menu_tap_gap`.
6. `python inside_track_bot.py result 4k` on a result screen — once after a
   win, once after a loss. It must print the winning horse's number both
   times, not "UNREADABLE".
7. Watch the printed races/hour, and check `python inside_track_bot.py stats`
   as the log fills up; a few hundred graded races are worth more than the
   charts in Part 1.

A bare `python inside_track_bot.py` no longer starts betting — it prints the
command list and exits. It used to default to `run`, which is one stray Enter
away from an accident.

Standing caveat: this is automating a live GTA Online money faucet. Rockstar
bans for it. Nothing here changes that.
