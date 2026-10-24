"""The static encounter bot's sound check and how it combines with the
flash check: the SFX_SHINE sequence in the audio says shiny, plain music
says normal, silence or no recorder leaves the picture to decide."""

import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import shine_sound  # noqa: E402
import static_encounter_bot as bot  # noqa: E402

SR = 32728


class FakeAudio:
    sr = SR
    error = None

    def __init__(self, x):
        self.x = x.astype(np.float32)

    def since(self, t0):
        return self.x


def music(seconds, seed=0):
    rng = np.random.default_rng(seed)
    out = []
    for _ in range(int(seconds * 8)):
        n = SR // 8
        t = np.arange(n) / SR
        chord = sum(np.sign(np.sin(2 * np.pi * f * t))
                    for f in rng.choice([131, 165, 196, 262, 330, 392], 3))
        out.append(chord / 3)
    return np.concatenate(out).astype(np.float32) * 0.3


def test_shine_in_audio_is_shiny():
    x = music(5)
    s = shine_sound.synth(SR) * 0.25
    i = int(1.5 * SR)
    x[i:i + len(s)] += s
    verdict, reason = bot.sound_check(FakeAudio(x), 0.0)
    assert verdict == "shiny", reason


def test_music_alone_is_normal():
    verdict, reason = bot.sound_check(FakeAudio(music(5)), 0.0)
    assert verdict == "normal", reason


def test_no_usable_audio_leaves_it_to_the_picture():
    assert bot.sound_check(None, 0.0)[0] is None
    assert bot.sound_check(FakeAudio(np.zeros(SR * 5)), 0.0)[0] is None
    assert bot.sound_check(FakeAudio(music(1)), 0.0)[0] is None   # too short


def test_combine():
    flash = lambda v: {"verdict": v, "reason": "picture"}
    assert bot.combine(flash("shiny"), "normal", "")["verdict"] == "shiny"
    assert bot.combine(flash("normal"), "shiny", "")["verdict"] == "shiny"
    assert bot.combine(flash("unsure"), "normal", "")["verdict"] == "normal"
    assert bot.combine(flash("normal"), "unsure", "")["verdict"] == "unsure"
    assert bot.combine(flash("unsure"), None, "")["verdict"] == "unsure"
    assert bot.combine(flash("normal"), None, "")["verdict"] == "normal"
