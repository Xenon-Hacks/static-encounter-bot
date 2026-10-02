# Static Encounter Shiny Hunter (Pokemon Crystal) -- V1

## What's new in V1 (vs. V0)

- **NTR-VC can be minimised / left in the background** (ported from the
  Sweet Scent bot v16). With the frame-sharing NTR-VC build the bot reads
  the picture from shared memory, and the freeze checks now work while the
  window is minimised: "Not Responding", "closed", and a stalled heartbeat
  (that last one only while the window is NOT minimised, so minimising
  never triggers a false pause). NTR-VC windows are recognised by title
  as well as NTR Viewer ones. See "Minimising NTR-VC" below.
- The 30-second freeze pause now says which problem it was.
- `test_shared_frame.py` added (checks the frame-sharing connection).
- **Fixed the occasional crash** `ValueError: operands could not be
  broadcast together with shapes (1029,) (0,)` in `sprite_id.find_game()`.
  It happened whenever the bot looked at a frame with no game picture in
  it (black screen / fade / stream dip): the picture width came out 0, and
  the maths broke. Now such a frame is treated as "nothing on screen yet"
  and the bot just keeps waiting. Also, an all-black frame no longer counts
  as "battle text shown".
- Removed the `SLOW_CYCLE_WARNING` log line -- it fired on ordinary
  15.2-15.4 s cycles and told you nothing.
- Kept from V0 unchanged: the crash-resilience catch-all in the main
  loop, the reset/mash logic, sprite detection, `MASH_TIMEOUT = 30`.

Built on the same proven code as the Sweet Scent / master bots -- species
and shiny detection, the freeze watchdog, the connection-quality checks,
the console click-freeze fix -- but for a **soft-reset (SR) static
encounter** instead of a grass encounter. There's no walking and no
fleeing at all here.

## Close InputRedirectionClient-Qt first (important)

Don't run InputRedirectionClient-Qt (or any other input tool connected to
the 3DS) while the bot runs. The bot sends its own inputs; a second
program sending "no buttons pressed" at the same time can make a single
bot press arrive twice, or not at all.

## The premise

You save your game standing right in front of the static encounter (a
stationary wild Pokemon that doesn't need a grass step to trigger --
e.g. a gift/event encounter or a Pokemon parked in a fixed spot). Every
attempt after that is identical:

1. **Soft reset** -- A + B + SELECT + START pressed together, the
   Game Boy/Color reset combo. This works from anywhere (overworld, a
   menu, even mid-battle), which is what makes it safe to call
   unconditionally at the top of every loop.
2. **Mash A** from the very first available frame -- through the boot
   logos, the title screen, into the CONTINUE prompt (already
   highlighted, since a save exists), and through any pre-battle
   dialogue -- until the wild Pokemon's battle starts on its own. No
   walking is needed: loading the save puts you right in front of it.
3. **Identify** the encounter (species + shiny/normal) the same way the
   Sweet Scent bot does, from the NORMAL/SHINY reference sprites.
4. If it's **not** shiny: go straight back to step 1. Soft-resetting
   reloads the exact same save, so there's nothing to flee from and no
   escape-cursor risk to manage.
5. If it **is** shiny (or ambiguous, or unrecognised): stop, alert you,
   and wait -- same as the other bots.

## Why this is simpler than Sweet Scent (and safer, differently)

The Sweet Scent bot's biggest source of complexity is that a wrong menu
press has real consequences (selecting FIGHT instead of RUN, walking the
character, etc.), so it verifies the cursor position with a screenshot
before nearly every confirming press.

None of that risk exists here:

* Soft-resetting throws away all progress since the last save on
  purpose -- that's the whole point of the method -- so "the bot pressed
  A on the wrong thing" during the mash phase is nothing, an on-console
  reboot with a battle you get to re-roll for. There's no permanent
  wrong state to land in.
* Every screen between the reset and the battle (logos, title,
  CONTINUE, dialogue) only ever advances on A, so there's no cursor to
  misplace in the first place.
* Because the reset combo works from *any* game state, it's also the
  bot's entire recovery mechanism. If the mash phase ever times out
  stuck somewhere, the next soft reset starts over clean -- no
  separate "stuck battle" recovery logic like the Sweet Scent bot
  needs.

The one thing worth checking by hand once: that CONTINUE (not NEW GAME)
really is what's highlighted when your save's title-screen prompt comes
up. That's the only way mashing A could ever confirm something you
didn't want.

## Party setup

None needed. There's no flee, so there's no speed/move requirement on
your lead Pokemon at all.

## Setup

1. `py -m pip install -r requirements.txt`
2. **Reuse your Sweet Scent/master calibration's sprite libraries.**
   Copy the `NORMAL/` and `SHINY/` folders from that bot's folder into
   this one. They're species-agnostic (not Route-34-specific), so they
   work for any static encounter without changes.
3. Run `py calibrate.py` and follow the 2 prompts:
   - drag a box around the whole NTR Viewer game view (skipped if
     you're using the frame-sharing build -- see below),
   - drag a box around a spot that visibly changes once a battle
     starts (e.g. where the HP box appears), captured once pre-battle
     and once with the static encounter's battle up.

## Running it

```
py static_encounter_bot.py --ip <3ds ip>
```

Start with your save standing right in front of the static encounter, in
the overworld, with no menu open -- **that** is the state every attempt
returns to. Each cycle prints its progress, e.g.:

```
  Soft-resetting (A+B+SELECT+START)...
  Battle started after 34 A presses.
[0.6 min] Encounter #1... Geodude (#1), normal colours (shiny-ness -0.05). Resetting.
```

`py test_reset.py --ip ...` runs a single soft-reset + mash-to-battle
cycle so you can confirm the timing works before leaving it unattended.

## Tuning

`reset_menu.py` has the constants that matter:

- `MASH_TIMEOUT` (30 s) -- how long the bot will keep mashing A before
  giving up on an attempt and soft-resetting fresh. Confirmed against
  ~2,500 real cycles (normally 13.6-15.4 s).
- `MASH_INTERVAL` (0.35 s) / `MASH_HOLD` (0.15 s) -- pace and hold
  length of each mashed A press.
- `RESET_HOLD` (0.3 s) / `RESET_RESEND` (8) -- how long the
  A+B+SELECT+START combo is held and how many times its packet is
  resent, since this goes out over unreliable UDP and a partial combo
  does nothing.

## How encounters are checked (any species)

Identical to the Sweet Scent bot: the NORMAL and SHINY folders hold a
reference sprite per species; the bot finds the Game Boy picture in the
capture, identifies the species from its silhouette/outline, and
measures its "shiny-ness" from where its colours sit between that
species' normal and shiny palettes. It never trusts a single unusual
look -- an ambiguous read gets re-checked (fresh frames) before it's
reported. See the Sweet Scent bot's README for the full detection
methodology and test results; nothing about it changed here.

## Minimising NTR-VC (frame-sharing build)

With the frame-sharing build of NTRViewer-HR (ntrviewer-hr-frame-share.zip,
see its FRAME_SHARE_README.md), the bot reads the game picture straight
from the viewer instead of off the screen, so NTR-VC can be minimised,
covered or moved anywhere while the bot runs. Button presses are
unaffected.

1. Start the frame-sharing ntrviewer.exe and connect it to the 3DS.
2. `py test_shared_frame.py` -- checks the connection and saves
   shared_frame_test.png. The game should be upright, with black bars left
   and right. If not, try `--rotation 0`, `2` or `3`, and put the one that
   works in config.json as `"shared_rotation": N`.
3. `py calibrate.py --shared` -- switches to the shared picture and
   recalibrates the battle indicator for it (the old screen-capture boxes
   don't carry over).
4. Run the bot as usual. It says "Reading frames from the frame-sharing NTR
   Viewer" at startup.

To go back to reading the screen: `py calibrate.py --screen`.

## If the 3DS, NTR Viewer or NTR-VC freezes

Before every press (each mashed A and the reset combo) the bot checks the
picture can be trusted. It can't if:

- NTR Viewer reports 0% connection quality;
- Windows reports NTR Viewer / NTR-VC as "Not Responding" (works even while
  minimised);
- NTR Viewer / NTR-VC was closed after the bot saw it running;
- with the frame-sharing NTR-VC: its heartbeat stops for 10 s while its
  window isn't minimised.

While any of these holds the bot presses nothing and waits. If it clears by
itself, the bot logs one line and carries on. Only after 30 seconds straight
does it pause, saying which one it was -- fix it and press ENTER, and it
soft-resets and starts fresh.

## Log files

Everything the bot prints is also saved to
`logs/static_encounter_<date>_<time>.txt`. To copy text from the console
WHILE the bot runs: right-click the window's title bar -> Edit -> Mark
(click-to-select is disabled on purpose, since a stray click used to
freeze the Sweet Scent bot the same way).

## If the bot ever freezes

`hang_report.txt` gets a traceback if the bot makes no progress for 3
minutes (it stays quiet while a deliberate pause is waiting for ENTER).
Send that file along with a screenshot if you need to debug it.

## Windows: `python` command acting weird?

Use `py` instead of `python` for every command.
