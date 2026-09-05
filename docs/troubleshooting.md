# When something goes wrong

[← back to the README](../README.md)

## Quirks worth knowing

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
`out/probe.png` before assuming the OCR broke.

**Don't touch the PS5's own controller while it runs.** A real input moves the
menu highlight out from under the bot, and it counts presses from where it
believes the cursor is.

**`result` only means anything on a result screen.** Run it while the board is
up and it will happily read a horse's saddle number, because the box happens
to sit there. The `result banner:` line it prints is the exception, and worth
checking both ways round — see [Knowing the race is over](race-detection.md).

**chiaki-ng's keyboard mapping has to be live** for `postmessage` and
`keyboard` modes: Cross = Enter, Circle = Backspace, which are the defaults.

**The fallback input modes need extra packages.** `postmessage` is the
default and needs nothing. Gamepad mode needs `vgamepad` and
[ViGEmBus](https://github.com/nefarius/ViGEmBus); keyboard mode needs
`pydirectinput`. Pick one with `--input-mode`, or set `input_mode` in the
config.

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

## Specific failures

**"No window matching 'chiaki'"** — chiaki-ng isn't running, is minimised, or
its title differs. Set `window_title` in the config.

**Odds read as `??`, or `trusted=False` every cycle** — the boxes have
drifted. Run `probe` and look at `out/probe.png`; if the red boxes aren't on
the odds, re-run `setup`. Check the window isn't covered.

**A price reads wrong in one lane only** — that box is probably clipping.
`EVENS` is the usual victim; see
[draw for the widest text](calibration.md#draw-the-boxes-for-the-widest-text-not-the-text-in-front-of-you).

**`win lane: UNREADABLE`** — run `result` on a real result screen, after a win
*and* after a loss. If it fails on both, the box is wrong; re-run `setup` and
measure it on a result screen. Races logged without a winner are dead weight:
they're excluded from `stats`, so the losses stop teaching you anything.

**Every race takes the full `race_wait_max`, and the log says
`settled=0`** — the `result_banner` box isn't matching, so the wait runs out
instead of ending on the banner. Run `result` on a result screen: if it says
`no match`, the box has orange backdrop in it or has missed the letters.
Re-run `setup` and redraw it inside the panel.

**`race_s` is identical in every row of the log** — nothing is being detected;
that number is just the floor. If the screen has a `result_banner` box, lower
`banner_wait_min` until `race_s` starts varying race to race. If it doesn't,
that constant is the whole point of measuring one.

**Races end early, on a screen with no result on it** — the opposite:
something during the race is matching the `result_banner` box. Run `result` on
the betting board and mid-race; anything but `no match` means the box is
somewhere too generic. `race_wait_min` is the backstop for this, so raise it
back to just inside the finish while you fix the box.

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
