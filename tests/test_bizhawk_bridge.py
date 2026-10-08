"""
End-to-end check of bizhawk_bot.py + bizhawk/bridge.lua without BizHawk or
a ROM: the real Lua script runs in a Lua 5.4 interpreter (the lupa
package) with BizHawk's comm/joypad/emu/memory functions stood in for by
a fake emulator that plays sim_battle's frames and talks to the bot over
a real socket, framed the way BizHawk's SocketServer.cs does it.

    py -m pip install lupa
    py tests/test_bizhawk_bridge.py
"""

import os
import socket
import sys
import threading

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path[:0] = [ROOT, HERE]

import bizhawk_bot                    # noqa: E402
import sim_battle                     # noqa: E402

PRESSES_TO_BATTLE = 25    # A presses from reset to the battle starting


class FakeGame:
    """Boot (needs A presses) -> sim_battle's battle start -> waits on the
    battle text until A+B+SELECT+START."""

    def __init__(self, shiny_attempts, seed=0):
        self.rng = np.random.default_rng(seed)
        self.shiny_attempts = shiny_attempts
        self.attempt = -1
        self.frame = 0
        self.held = {}
        self.battle_mode = 0
        self.dvs = (0, 0)
        self._new_attempt()

    def _new_attempt(self):
        self.attempt += 1
        self.presses, self.was_a = 0, False
        self.seq = None
        self.image = np.full((144, 160, 3), 248, np.uint8)
        self.battle_mode = 0

    def _start_battle(self):
        shiny = self.attempt in self.shiny_attempts
        self.dvs = (0xEA, 0xAA) if shiny else (int(self.rng.integers(0, 256)), 0x37)
        self.seq = iter(list(sim_battle.frames(shiny, self.rng)))

    def advance(self):
        self.frame += 1
        h = self.held
        combo = all(h.get(b) for b in ("A", "B", "Select", "Start"))
        was, self.was_combo = getattr(self, "was_combo", False), combo
        if combo:
            if not was:
                self._new_attempt()
            return
        if self.seq is None:
            a = bool(h.get("A"))
            if a and not self.was_a:
                self.presses += 1
            self.was_a = a
            if self.presses >= PRESSES_TO_BATTLE:
                self._start_battle()
            return
        nxt = next(self.seq, None)
        if nxt is None:
            return                     # stays on the battle text
        _, img, phase = nxt
        self.image = img
        if phase in ("slide", "battle", "flash", "sparkle", "cry", "text"):
            self.battle_mode = 1

    def readbyte(self, offset):
        addr = offset + 0xC000
        return {0xD22D: self.battle_mode, 0xD20C: self.dvs[0],
                0xD20D: self.dvs[1], 0xCFCC: 0x01}.get(addr, 0)


class FakeBizHawk:
    """BizHawk's Lua API, as far as bridge.lua uses it."""

    def __init__(self, game, port):
        self.game = game
        self.sock = socket.create_connection(("127.0.0.1", port))
        self.paused = False
        self.logs = []

    def _send(self, payload):
        self.sock.sendall(str(len(payload)).encode() + b" " + payload)

    def _receive(self):
        digits = b""
        while True:
            c = self.sock.recv(1)
            if c in (b" ", b""):
                break
            digits += c
        n, buf = int(digits or 0), b""
        while len(buf) < n:
            buf += self.sock.recv(n - len(buf))
        return buf.decode()

    def install(self, lua):
        g = lua.globals()
        api = self

        def table(**kw):
            t = lua.table()
            for k, v in kw.items():
                t[k] = v
            return t

        def screenshot(path):
            cv2.imwrite(path, api.game.image)

        def joypad_set(t):
            api.game.held = {k: bool(v) for k, v in t.items()}

        g.comm = table(socketServerSend=lambda s: api._send(s.encode()),
                       socketServerResponse=api._receive,
                       socketServerGetInfo=lambda: "127.0.0.1")
        g.joypad = table(get=lambda: table(A=False, B=False, Select=False, Start=False),
                         set=joypad_set)
        g.emu = table(frameadvance=self.game.advance,
                      framecount=lambda: self.game.frame,
                      limitframerate=lambda on: None)
        g.memory = table(readbyte=lambda off, dom: self.game.readbyte(off))
        g.client = table(pause=lambda: setattr(api, "paused", True),
                         screenshot=screenshot)
        g.console = table(log=lambda s: api.logs.append(s))


def run(shiny_attempts, port):
    from lupa import lua54
    game = FakeGame(shiny_attempts)
    out = {}

    def bot():
        sys.argv = ["bizhawk_bot.py", "--port", str(port), "--check-dvs", "--seed", "1"]
        bizhawk_bot.start_emuhawk = lambda args, port: None
        bizhawk_bot.main()
        out["done"] = True

    t = threading.Thread(target=bot, daemon=True)
    t.start()
    import time
    time.sleep(0.5)
    hawk = FakeBizHawk(game, port)
    lua = lua54.LuaRuntime()
    hawk.install(lua)
    with open(os.path.join(ROOT, "bizhawk", "bridge.lua")) as f:
        lua.execute(f.read())
    t.join(30)
    return game, hawk, out


def test_stops_on_the_first_shiny():
    os.chdir(os.path.join(ROOT, "tests"))      # logs/ and alerts/ land here
    game, hawk, out = run({3}, 43901)
    assert out.get("done"), "bot didn't finish"
    assert hawk.paused, "EmuHawk wasn't paused for the shiny"
    assert game.attempt == 3, game.attempt
    assert game.battle_mode == 1


if __name__ == "__main__":
    test_stops_on_the_first_shiny()
    print("test_stops_on_the_first_shiny: ok")
