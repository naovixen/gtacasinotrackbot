# Knowing the race is over

[← back to the README](../README.md)

The race is the floor on cycle time — everything else in a cycle put together
costs less than it does — so how the bot decides it has ended is worth more
than any other timing in the config.

## Why stillness isn't the signal

Originally it decided by watching the picture stop moving. That looks right
and isn't: **when a race finishes the camera holds on the horses for somewhere
between half a second and three seconds** before the result screen comes up,
and a held camera is exactly as still as a finished screen. Anything quick
enough to catch the short hold fires during the long one, on a screen with no
result on it; anything patient enough not to has to be patient in every race,
including the ones where the hold was half a second. `race_wait_min` was
paying for the worst case, every race.

## What it looks for instead

So the bot looks for the result screen. **The RESULTS title panel is the same
every race** — a near-black box with yellow letters, at the top of the screen,
nowhere near the two things that do differ (which horse won, and what the bet
paid). The `result_banner` box is matched on those two colours: mostly
near-black, some yellow in it. Not OCR — two pixel counts over a small crop,
about a millisecond, so it can be asked twenty times a second for the whole
wait and cost nothing. Two matching frames in a row are needed, against a
single odd frame caught mid-fade.

Nothing waits for the screen to settle afterwards. The cards, the prices and
the banner all arrive together, so there is nothing to settle for — and a
stillness check here is worse than useless, because the chip counter ticks up
on this screen and two consecutive quiet frames often never come. If a lane
number is ever caught mid-draw, `read_win_lane()` simply asks again.

## The two floors

That splits the floor in two, because what it has to do depends on which
signal ends the wait:

| setting | used when | what it has to clear | default |
| --- | --- | --- | --- |
| `banner_wait_min` | there's a `result_banner` box | only the screens between the bet and the start | 25.0 |
| `race_wait_min` | there isn't | the finish *and* the 0.5–3s camera hold after it | 33.0 |

`banner_wait_min` is not a guess at when the race ends — the banner says that.
One poll costs ~7ms, so looking early is close to free and it can come down a
long way. Take it down in steps and watch the `race_s` column in
`data/race_log.csv`: while `race_s` keeps landing on the same value every
race, the floor is still what you're waiting on; once it starts varying race
to race the banner has taken over and there is nothing left to win.

## Checking the box

`python -m insidetrack result` prints what the matcher sees:

```
result banner: MATCHES  (90% near-black, 9% yellow)
```

Run it on a result screen and it should say `MATCHES`; run it on the betting
board and it should not. Both halves matter — a box that matches everything
ends the race wait the moment it starts looking. The one thing that breaks it
is the orange backdrop leaking into the box, so keep it inside the panel.

Without a `result_banner` box nothing changes: the wait falls back to
stillness, `race_wait_min` has to stay generous, and the bot says so at
startup.

## For scale

The pieces measured on this machine:

| step | cost |
| --- | --- |
| one banner check (grab + two pixel counts) | 7 ms |
| `read_win_lane()`, landing first try | 39 ms |
| one full-window stillness frame | 30 ms |
