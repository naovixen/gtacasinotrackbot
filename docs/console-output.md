# Reading the console output

[← back to the README](../README.md)

Per race the bot prints the odds it read, what it decided, the result, and a
running session tally:

```
profile   second
strategy  pickorder
timings   trimmed
input     postmessage
log       E:\gtacasinotrackbot\data\race_log.csv
race end  on the RESULTS banner
keys      ScrollLock pauses, Ctrl-C stops

time      lane     1       2       3       4       5       6
21:04:12  board    EVENS   5/1     13/1    4/1     26/1    20/1
          bet      lane 1  EVENS   MAX     10,000
          result   lane 1  EVENS   WON     +10,000
          session  1/1 won                 +10,000
          session  37.4s/r    +100.0% ROI  +374,000/h
```

`37.4s/r` is seconds per race, end to end. `+374,000/h` is what that rate
implies at the strategy's average return per race — not what this session has
actually made; the realised figure is the running net on the line above.

The settings are a line each, flush left with the timestamps below them. Only
the settings: which HWND the keys go to and what to do if the menu doesn't
move is first-run troubleshooting, and it was printing in full before every
run after that too. The two input modes that carry a real caution rather than
a description still get it as small print under the value — a virtual pad is
system-wide, and keyboard mode types into whatever is focused.

## How the grid is built

The races are a grid, because that's output you scan for hours rather than
read. Five rules hold the grid together:

- **Money reads down one column.** The stake, the race's profit, the running
  net and the hourly rate all start in the same place, which is what decides
  the field widths on the session line rather than the other way round.
- **One cell width for everything.** Every value sits in an 8-column cell —
  wide enough for `lane 1`, the longest of them, plus a two-space gap — so the
  prices on a `bet` row land in the same columns as the prices on the `board`
  row above it. Per-column widths were internally correct and still read as
  ragged.
- **Nothing runs past the width of a board row** (64 columns — five padded
  cells and a sixth as long as the price in it). A longer message wraps onto
  the next line, still on the grid.
- **Nothing is ever appended to a line.** Warnings and errors get their own
  row, tagged and coloured — including the ones from the machine and the
  controller, which is why `recovering` no longer sits at its own indent.
- **At most one thing per line is bright**, and it's the thing you're scanning
  for: the backed price on the board row, `MAX`/`MIN` on the bet row,
  `WON`/`LOST` and what it made on the result row, the running net on the
  session row. Timestamps, tags, units and asides are grey and recede.

`bet` and `result` share their cells deliberately. What you backed sits
directly above what won, so whether they match is a matter of the two lines
*looking* the same rather than of reading either of them.

There's no `$` on the amounts — every figure is in the same chips, so a symbol
on each one is a column of noise that says nothing and pushes the digits out of
line as soon as a sign appears next to it.

## Colour

Colour turns itself off when it would be noise: piped or redirected output, or
`NO_COLOR` set ([no-color.org](https://no-color.org)). `--no-colour` forces
plain text, `FORCE_COLOR=1` forces it on. On Windows the console understands
ANSI but starts with it switched off, so the bot enables it once at startup —
that covers PowerShell in both Windows Terminal and the older console host, and
only ASCII is used, so there's nothing for a code page to mangle.

## The log

Every race is appended to `data/race_log.csv` — odds, choice, reason, stake,
winner, payout, timings. `python -m insidetrack stats` reads it back; see
[the strategy notes](strategy.md) for what to do with it.
