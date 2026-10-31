# How it works

[← back to the README](../README.md)

The package is layered so each piece can be tested without the game running.
`app.build()` assembles the object graph; nothing constructs its own
collaborators, so a test can hand `BoardReader` a fake screen and a scripted
recogniser.

## The modules

| module | what it owns |
| --- | --- |
| `config` | profile / timing / settings shapes — data only |
| `userconfig` | `insidetrack.toml`: read, validated, written |
| `wizard` / `picker` | `setup`: the walkthrough, and the window you click on |
| `paths` | where the project keeps things: `data/`, `out/` |
| `screen` | capture, and "has the picture stopped moving?" |
| `vision` | numpy preprocessing of a captured box |
| `ocr` | the recogniser, wrapped |
| `parsing` | text → odds, money, lane numbers |
| `board` | what the bot learns by looking |
| `backends` / `controller` | getting a keypress to the PS5, and making it land |
| `machine` | the betting machine as a sequence of screens |
| `strategy` | which horse, and what the race was worth |
| `racelog` / `stats` | the record, and reading it back |
| `console` | colour and alignment for everything printed |
| `loop` | the race cycle |
| `app` / `cli` / `diagnostics` / `tuning` | wiring and the commands |

## Load-bearing decisions

**Nothing is timed by sleeping if it can be measured instead.** A press is
confirmed by watching whether the screen reacted, and the end of a race is
read off the result screen itself rather than waited out — see
[Knowing the race is over](race-detection.md). Where stillness is still the
signal, the test adapts to how much motion an animation actually showed,
because a busy result screen never gets as quiet as an idle menu.

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

## Repository layout

| path | what |
| --- | --- |
| `insidetrack/` | the bot |
| `inside_track_bot.py` | entry point, kept so the old commands still work |
| `insidetrack.example.toml` | config template — copy it, or run `setup` |
| `insidetrack.toml` | **your** boxes and settings (not committed) |
| `data/race_log.csv` | your own race-by-race record, appended forever |
| `analysis/validate.py` | reproduces the strategy analysis |
| `analysis/parse_races.py` | parses the published race logs |
| `post-info/` | the strategy author's original posts, which you add yourself (not committed) |
| `docs/` | these notes |
| `out/` | what the bot generates — calibration and setup captures, debug crops (not committed) |
