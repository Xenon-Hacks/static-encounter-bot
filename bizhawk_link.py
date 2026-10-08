"""
bizhawk_link.py -- the bot's side of the BizHawk connection (the other side
is bizhawk/bridge.lua, running inside EmuHawk).

EmuHawk connects to us (it's started with --socket_ip/--socket_port), and
then every message in either direction is "<length> <bytes>". Each turn
the script sends a state line and waits for a command; the command says
how many frames to play and where to save a screenshot of the last one.
So the game only moves when the bot says so: no frame is ever missed.
"""

import collections
import os
import socket

import cv2
import numpy as np

State = collections.namedtuple("State", "frame battle_mode dv1 dv2 options")
Observation = collections.namedtuple("Observation", "state image")

BATTLE_SCENE_OFF = 1 << 7     # wOptions bit 7 (constants/ram_constants.asm)


class LinkClosed(Exception):
    pass


class BizHawkLink:
    def __init__(self, port, host="127.0.0.1", frame_path="bizhawk_frame.png"):
        self.frame_path = os.path.abspath(frame_path)
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server.bind((host, port))
        self.server.listen(1)
        self.conn = None
        self._buf = b""

    def accept(self, timeout):
        """Waits for EmuHawk to connect. Returns False on timeout."""
        self.server.settimeout(timeout)
        try:
            self.conn, _ = self.server.accept()
        except socket.timeout:
            return False
        self.conn.settimeout(None)
        self.conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        return True

    # ------------------------------------------------------------ framing
    def _read(self, n):
        while len(self._buf) < n:
            chunk = self.conn.recv(max(65536, n - len(self._buf)))
            if not chunk:
                raise LinkClosed("EmuHawk closed the connection")
            self._buf += chunk
        out, self._buf = self._buf[:n], self._buf[n:]
        return out

    def _read_message(self):
        digits = b""
        while True:
            c = self._read(1)
            if c == b" ":
                break
            if not c.isdigit() or len(digits) > 10:
                raise LinkClosed(f"garbled message from EmuHawk ({digits + c!r})")
            digits += c
        return self._read(int(digits))

    def _send(self, text):
        data = text.encode()
        self.conn.sendall(str(len(data)).encode() + b" " + data)

    # ------------------------------------------------------------ public
    def observe(self, image=False):
        """The state line EmuHawk sends for the current frame, plus the
        screenshot it just saved if `image`."""
        line = self._read_message().decode(errors="replace").split()
        if len(line) != 6 or line[0] != "S":
            raise LinkClosed(f"unexpected state line from EmuHawk: {line}")
        state = State(*map(int, line[1:]))
        picture = None
        if image:
            with open(self.frame_path, "rb") as f:
                png = f.read()
            picture = cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_COLOR)
            if picture is None:
                raise LinkClosed(f"couldn't read EmuHawk's screenshot {self.frame_path}")
        return Observation(state, picture)

    def step(self, buttons=(), frames=1):
        """Holds `buttons` (e.g. ("A",) or ("A", "B", "Select", "Start"))
        for `frames` frames, then returns the new frame's Observation."""
        self._send(f"P {','.join(buttons) or '-'} {int(frames)} {self.frame_path}")
        return self.observe(image=True)

    def stop(self):
        """Hands the game back: the script pauses EmuHawk and ends."""
        try:
            self._send("STOP")
        except OSError:
            pass

    def close(self):
        for s in (self.conn, self.server):
            try:
                if s is not None:
                    s.close()
            except OSError:
                pass


def is_shiny_dvs(dv1, dv2):
    """Gen II shininess from the DV bytes (attack/defense, speed/special):
    defense, speed and special all 10, attack 2, 3, 6, 7, 10, 11, 14 or 15."""
    attack, defense = dv1 >> 4, dv1 & 0xF
    speed, special = dv2 >> 4, dv2 & 0xF
    return defense == 10 and speed == 10 and special == 10 and bool(attack & 2)
