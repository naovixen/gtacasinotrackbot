# Configuration reference

[← back to the README](../README.md)

Everything lives in **`insidetrack.toml`**, next to you or next to the
package. It is not committed — it is specific to your window — and
`insidetrack.example.toml` is the template documenting every setting.

`python -m insidetrack setup` writes this file for you. You only need this
page if you want to edit it by hand.

## Shape of the file

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
result_banner = [1210, 60, 480, 180]
```

## Boxes

Boxes are `[left, top, width, height]` in pixels **from the top-left of the
chiaki-ng window**, not of the screen. The corner form
`{ left = .., top = .., right = .., bottom = .. }` works anywhere too, and for
the odds you can give just `odds_lane1` and `odds_lane6` and let the four
between be spaced evenly.

Keep one `[screens.NAME]` block per layout — per monitor, per window size —
and pick between them with `--screen`.

See [Measuring the boxes](calibration.md) for how to draw them so they keep
reading correctly.

## Every command-line option

The README lists the four you'll actually reach for. In full:

| option | effect |
| --- | --- |
| `--screen NAME` | which `[screens.NAME]` block to use |
| `--config PATH` | a config file somewhere other than next to you |
| `--dry` | decide and log, send no input |
| `--strategy pickorder\|chart` | override the strategy for this run |
| `--input-mode postmessage\|gamepad\|keyboard` | override the input backend |
| `--debug-images` | save what the recogniser was actually given |
| `--no-colour` | plain text (also `NO_COLOR=1`; off automatically when piped) |
| `--window TITLE` | part of the stream window's title, if it is not `chiaki` |

`setup` takes three more: `--example`, `--manual` and `--point`, described in
[Measuring the boxes](calibration.md#if-youd-rather-not-use-the-wizard).

`python inside_track_bot.py <command>` runs the same thing, kept as an entry
point so the older commands still work.

## Input mode

`postmessage` is the default and needs no extra packages. `gamepad` needs
`vgamepad` plus [ViGEmBus](https://github.com/nefarius/ViGEmBus), and
`keyboard` needs `pydirectinput` — both carry cautions worth reading in
[troubleshooting](troubleshooting.md#quirks-worth-knowing).

## Where the config is looked for

In this order: `--config PATH`, then `$INSIDETRACK_CONFIG`, then
`insidetrack.toml` in the working directory, then beside the package, then
`~/.insidetrack.toml`.

## Timing

An optional `[timing]` block, which you should not need unless navigation
starts dropping presses:

```toml
[timing]
transition_gap = [0.4, 0.5]    # raise this FIRST if presses go missing
menu_tap_gap = [0.05, 0.06]    # then this
```

## Race-wait floors

Two settings decide the minimum a race is allowed to take. Which one applies
depends on whether the screen has a `result_banner` box:

| setting | used when | what it has to clear | default |
| --- | --- | --- | --- |
| `banner_wait_min` | there's a `result_banner` box | only the screens between the bet and the start | 25.0 |
| `race_wait_min` | there isn't | the finish *and* the 0.5–3s camera hold after it | 33.0 |

Tuning `banner_wait_min` is the single biggest lever on throughput —
[Knowing the race is over](race-detection.md) explains why and how far down it
can come.
