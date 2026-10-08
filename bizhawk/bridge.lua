-- bridge.lua -- runs inside BizHawk (EmuHawk) and lets bizhawk_bot.py play
-- the game one frame at a time over BizHawk's socket connection.
--
-- Don't load this by hand: bizhawk_bot.py starts EmuHawk with it (or prints
-- the exact command to start it with). EmuHawk has to be started with
-- --socket_ip and --socket_port for the connection to exist.
--
-- Each turn it sends the bot one line of game state:
--   "S <frame> <battle mode> <dv1> <dv2> <options>"
-- and waits for one command back:
--   "P <buttons> <n> <png path>"  hold these buttons (comma-separated, "-"
--                      for none) for n frames, save a screenshot of the
--                      last one to <png path>, then report again
--   "STOP"             pause the emulator and end this script, handing the
--                      game back to you
-- (The picture goes through a file rather than BizHawk's socket screenshot
-- so that each turn is exactly one message each way. Two messages in a row
-- from EmuHawk can sit in Windows' TCP buffers for up to 200 ms each time.)
--
-- The RAM addresses are the same in Crystal 1.0 and 1.1 (pret/pokecrystal
-- symbol files): wBattleMode D22D, wEnemyMonDVs D20C-D20D, wOptions CFCC.
-- They're only read to know when a battle has started, to warn if Battle
-- Scene is off, and (only with --check-dvs) to cross-check the flash.

local BATTLE_MODE = 0xD22D
local ENEMY_DVS = 0xD20C
local OPTIONS = 0xCFCC

local function wram(addr)
  -- the "WRAM" domain is all 8 banks back to back; C000-CFFF is bank 0
  -- and D000-DFFF here is bank 1, so the offset is just addr - C000
  return memory.readbyte(addr - 0xC000, "WRAM")
end

-- Game Boy buttons are "A", "B", ... on some BizHawk cores and "P1 A",
-- "P1 B", ... on others.
local prefix = ""
local pad = joypad.get()
if pad["P1 A"] ~= nil then
  prefix = "P1 "
end

local function buttons(list)
  local t = {}
  if list ~= "-" then
    for name in string.gmatch(list, "[^,]+") do
      t[prefix .. name] = true
    end
  end
  return t
end

emu.limitframerate(false)   -- run as fast as the bot can keep up
console.log("bridge.lua: connected to the bot at " .. comm.socketServerGetInfo())

local running = true
while running do
  comm.socketServerSend(string.format("S %d %d %d %d %d",
    emu.framecount(), wram(BATTLE_MODE), wram(ENEMY_DVS),
    wram(ENEMY_DVS + 1), wram(OPTIONS)))
  local cmd = comm.socketServerResponse()
  if cmd == nil or cmd == "" or cmd == "STOP" then
    running = false
  else
    local list, n, path = string.match(cmd, "^P (%S+) (%d+) (.+)$")
    if list == nil then
      console.log("bridge.lua: unexpected command from the bot: " .. tostring(cmd))
      running = false
    else
      local held = buttons(list)
      for _ = 1, tonumber(n) do
        joypad.set(held)
        emu.frameadvance()
      end
      client.screenshot(path)
    end
  end
end

emu.limitframerate(true)
client.pause()
console.log("bridge.lua: the bot handed the game back to you (emulator paused).")
