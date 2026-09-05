# insidetrack

An auto-bettor for GTA Online's **Inside Track** horse racing machine, driving
a PS5 over [chiaki-ng](https://github.com/streetpea/chiaki-ng) Remote Play.

It watches the betting board, reads the six horses' odds, picks one, places a
maximum bet, waits out the race, records the result, and starts again. Around
47 seconds a race, unattended.

> **This automates a live GTA Online money faucet. It violates Rockstar's
> Terms of Service, and people get banned and wiped for it.** Nothing in this
> repo changes that. Supervise it, and don't run it on an account you care
> about.

Roughly **$270k–$480k an hour**, with a lot of variance — an hour well below
that is normal, not a broken bot.
[The numbers, and where they come from →](docs/strategy.md)

---

## What you need

- **Windows** and **Python 3.11+**
- **chiaki-ng**, streaming your PS5, with GTA Online open
- The Python packages:

  ```
  pip install easyocr opencv-python numpy mss pygetwindow pillow
  ```

  `easyocr` is the big one — it pulls in PyTorch, and the first run downloads
  its models.

---

## Setting it up

**1. Tell it where things are on your screen.** The bot works from pixels in
your chiaki-ng window, so it has to be shown where to look. This takes about
two minutes and only has to be done once:

```
python -m insidetrack setup
```

It walks you through five screens — put the game on the one it names, press
Enter, and click the corners of the box it asks for. It grabs a still picture
to click on, so the game can carry on in the background.

> **One thing that catches everyone:** draw each box around the *widest* text
> it will ever hold, not the text you can see right now. A box drawn snugly
> around `2/1` will clip every `EVENS` from then on. Extra room inside a box
> costs nothing.
> [Why this matters →](docs/calibration.md#draw-the-boxes-for-the-widest-text-not-the-text-in-front-of-you)

**2. Check it worked.**

```
python -m insidetrack probe    # saves a picture with the boxes drawn on
python -m insidetrack read     # one board read, and what it would bet
python -m insidetrack keys     # confirm the PS5 is receiving input
```

Open `out/probe.png` — the coloured boxes should sit on the odds, the stake
and the winning lane.

[Full setup guide →](docs/calibration.md)

---

## Running it

**Rehearse first.** `--dry` decides and logs but sends no input at all:

```
python -m insidetrack run --dry
```

Open the SINGLE EVENT board by hand, let it read a few boards, and check the
decisions look sensible. Then, for real — start it from the machine's start
screen:

```
python -m insidetrack run
```

**ScrollLock pauses it** at any time, from any window, even while you're using
something else. Turn it off to resume. **Ctrl-C stops it.**

You don't need to keep chiaki-ng focused, so you can carry on using the PC —
but the window has to stay **visible and unobscured**. Don't drag anything
over the stream, and don't minimise it.

Every race is written to `data/race_log.csv`. To see how you're actually
doing:

```
python -m insidetrack stats
```

[What the output means →](docs/console-output.md)

---

## Commands

```
python -m insidetrack <command> [options]
```

| command | what it does |
| --- | --- |
| `setup` | measure this screen's boxes (run this first) |
| `run` | place bets until stopped |
| `stats` | what your own bets have returned |
| `read` | one board read, and what it would do with it |
| `result` | check it can read a result screen |
| `probe` | save pictures with the boxes drawn, to check them |
| `keys` | find which window chiaki-ng takes input on |
| `tune` | check the timings against the real menu (~1 min, no bets) |
| `budget` | estimated races and $/hour from your timings |

| option | effect |
| --- | --- |
| `--dry` | decide and log, send no input |
| `--screen NAME` | use a different screen layout |
| `--config PATH` | use a config file somewhere else |
| `--no-colour` | plain text output |

---

## A few things to know

- **Don't touch the PS5's controller while it runs.** It moves the menu out
  from under the bot.
- **Re-run `setup` if the chiaki-ng window moves or resizes.** The boxes are
  measured for one window size.
- **A skip is still a bet.** On a bad board it places the $100 minimum rather
  than backing out, which is safer than leaving and re-entering.
- **If the winning lane can't be read, the race is logged blank, not guessed.**
  Those races are left out of your stats.

---

## Something's wrong

Most problems are a box that has drifted or was drawn too tight. Run `probe`
and look at `out/probe.png` first.

[Troubleshooting, symptom by symptom →](docs/troubleshooting.md)

---

## More detail

| | |
| --- | --- |
| [The strategy and its numbers](docs/strategy.md) | which horse it backs, and the evidence |
| [Measuring the boxes](docs/calibration.md) | the full setup walkthrough |
| [Reading the output](docs/console-output.md) | what each line and colour means |
| [Configuration](docs/configuration.md) | every setting in `insidetrack.toml` |
| [Troubleshooting](docs/troubleshooting.md) | quirks and specific failures |
| [Knowing the race is over](docs/race-detection.md) | the biggest lever on speed |
| [How it works](docs/architecture.md) | internals and repository layout |
