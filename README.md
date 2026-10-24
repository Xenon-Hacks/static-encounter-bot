# Static Encounter Shiny Hunter (Pokemon Crystal) -- V3

## What's new in V3: it listens for the shiny sound too

Ported from the Sweet Scent bot (v26):

- **SFX_SHINE check** (`shine_sound.py`). A shiny's animation plays
  SFX_SHINE eight times (a square wave stepping 512 -> 683 -> 1024 -> 2048
  -> 4096 Hz, about 0.8 s in all). Nothing else in a wild battle sounds
  like it. The bot matches that exact sound against the game audio of each
  battle's start. Either check seeing a shiny is enough to stop; a clear
  "no shiny sound" settles a battle whose picture had gaps, so the bot
  stops to ask you less often.
- **Where the audio comes from.** With NTR-VC 2.2.0 or later the bot reads
  the game audio straight from NTR-VC's shared memory (`shared_audio.py`),
  so NTR-VC can be muted, at 0 volume, or on any output, and other
  programs' sound never gets in. Turn NTR-VC's audio on in its Debug
  window: Audio (NTR-HR+). With an older NTR-VC it records the PC's
  speakers instead (`audio_recorder.py`, needs `soundcard`); there NTR-VC
  must not be muted, and `--audio-device "Steam Streaming"` picks another
  output.
- Thresholds as measured on the real 3DS by the Sweet Scent bot: 35 forced
  shinies scored 0.12-0.23, about 50,000 normal encounters never went
  above 0.09. At 0.11 or more the bot calls it shiny, under 0.10 normal,
  in between it asks you. The PC-speaker path is noisier (normals reached
  0.13), so it can false-alarm; it never resets a shiny away.
- The bot only listens to the last 3 s before the battle appeared and
  after, never to the boot logos and title screen.
- New options: `--no-sound` (flash only), `--loopback` (PC speakers even
  when NTR-VC shares its audio), `--audio-device NAME`.
- **Flash check fixes** from the Sweet Scent bot: on the Game Boy Color only
  the battle field turns black during the flash (the Pokemon and the text
  box stay lit), so the check now looks at the field alone, and it keeps
  track of where the game sits in NTR-VC's frame while the screen is dark.
  Before, the real flash could be watered down to a missed shiny.
- **Battle Scene doesn't matter** for the 3DS bot: with it off the game
  only skips move animations, and the shiny flash and sound still play.
  (The BizHawk bot still stops when Battle Scene is off.)
- The BizHawk bot doesn't use the sound: it sees every frame, so the flash
  can't be missed there.
- `tests/` adds the sound detector, the shared-audio reader and the bot's
  sound/flash verdicts.

## What was new in V2: no Pokemon sprites anywhere

- **Shinies are spotted by their animation, not their colours.** When a
  wild Pokemon is shiny, Crystal plays the shiny animation before its HP
  box appears: the whole battle screen flashes to a photo-negative for 5
  frames (the "black flash"), then sparkles circle it. A normal one gets no
  animation at all. The bot watches for that flash (`shiny_flash.py`).
  It works the same for every species, so the `NORMAL/` and `SHINY/`
  sprite folders and `sprite_id.py` are gone, and nothing here contains
  any Pokemon graphics.
- **New: run it in BizHawk** (`bizhawk_bot.py`). The emulator plays the
  game one frame at a time for the bot, so the flash can never be missed,
  it runs faster than real time, and there's nothing to calibrate. See
  "Running it in BizHawk" below.
- The 3DS bot uses the same flash check. It now records frames non-stop
  on a background thread (`frame_recorder.py`) so the 83 ms flash can't
  slip past between button presses.
- **Battle Scene must be ON** in the game's OPTIONS. With it off the game
  skips battle animations, the shiny one included.
- What it no longer does: name the species. It only says shiny or not.
- `tests/` checks the flash detector against simulated battle starts and
  the BizHawk link against a stand-in emulator (no ROM needed).

How the flash was pinned down, in the pokecrystal decompile
(github.com/pret/pokecrystal): `BattleStartMessage` in
`engine/battle/core.asm` plays `ANIM_SEND_OUT_MON` only when
`BattleCheckEnemyShininess` says shiny; its `.Shiny` branch in
`data/moves/animations.asm` starts with `BATTLE_BG_EFFECT_FLASH_INVERTED`,
which (`engine/battle_anims/bg_effects.asm`) reverses the background
palette for 5 frames. The 3DS Virtual Console's anti-flashing patch only
touches a few move animations, not this one.

## Running it in BizHawk

1. Install BizHawk (EmuHawk) and `py -m pip install -r requirements.txt`.
2. Put your Crystal save next to the ROM the way BizHawk expects it
   (load the ROM once, then File > Save RAM shows where), saved standing
   right in front of the static encounter, with Battle Scene ON.
3. Run:

   ```
   py bizhawk_bot.py --emuhawk C:\path\to\EmuHawk.exe --rom C:\path\to\crystal.gbc
   ```

   The bot starts EmuHawk with the options it needs (`--socket_ip`,
   `--socket_port`, `--lua=bizhawk\bridge.lua`). Without `--emuhawk` it
   prints the exact command for you to start EmuHawk yourself.
4. When it finds a shiny (or can't tell), it pauses EmuHawk on the battle
   screen, saves a screenshot to `alerts/`, and stops. The game is yours.

Each attempt: soft reset, wait a random number of frames, mash A at a
random pace until the battle starts, then press nothing and watch every
frame until "Wild X appeared!". The randomness matters: an emulator is
exact, so identical presses would give the identical Pokemon every time.

The bot reads three things from the game's RAM: whether a battle has
started (`wBattleMode`), the Battle Scene option (it stops and tells you
if it's off), and, only with `--check-dvs`, the Pokemon's DVs. With
`--check-dvs` it stops if the flash and the DVs ever disagree, which is a
good way to confirm the flash check on your setup for the first few
hundred resets.

In EmuHawk, leave "Screenshot capture OSD" off (the default), so the
pictures the bot reads have no on-screen messages in them.

## What was new in V1 (vs. V0)

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

Built on the same proven code as the Sweet Scent / master bots -- the
freeze watchdog, the connection-quality checks,
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
3. **Check** whether the shiny animation's flash played while the battle
   was starting.
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
2. Run `py calibrate.py` and follow the 2 prompts:
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
[0.6 min] Encounter #1... normal (no shiny flash). Resetting.
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

A background thread grabs frames as fast as it can from the moment of each
soft reset. Once "Wild X appeared!" is on screen, the bot looks back over
the frames since the battle transition went black, for a short burst of
photo-negative frames between two normal battle screens. Found: shiny.
Not found: normal. It also listens to the battle's start for the
shiny sound (see V3 above); either one finding a shiny stops the bot, and
a clear "no shiny sound" counts as normal. If it can't be sure (for example the frames came in
more than 75 ms apart, so a 83 ms flash could have fallen between two of
them), it stops and asks you rather than risk resetting a shiny away.

This needs NTR Viewer to stream smoothly. With the frame-sharing build the
bot knows the real gap between stream frames and will tell you if the
stream is too slow; when it reads the screen it can't tell a repeated
stream frame from a still picture, so keep the stream quality up. BizHawk
doesn't have this problem at all.

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
