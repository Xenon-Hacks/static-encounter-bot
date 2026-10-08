"""
frame_recorder.py -- grabs frames non-stop on a background thread so the
shiny flash (5 game frames, ~83 ms) can't slip by while the main loop is
busy pressing buttons. Wraps a vision.Capture or shared_frame capture and
is a drop-in replacement for it: .frame() returns the latest frame.

With the frame-sharing viewer only NEW pictures are recorded (it counts
the frames it decodes), so the gaps shiny_flash sees are the real gaps
between stream frames, and a slow stream shows up as "unsure" instead of
quietly missing a shiny. A screen grab can't tell a repeated stream frame
from a still screen, so there every grab counts: reading the screen
relies on NTR Viewer streaming smoothly (see the README).
"""

import threading
import time

import numpy as np

import gb_screen
import shiny_flash


class RecordingCapture:
    def __init__(self, cap, keep_seconds=60.0):
        self.cap = cap
        self.recorder = shiny_flash.FlashRecorder(keep_seconds)
        self._lock = threading.Lock()
        self._latest = None
        self._error = None
        self._stop = False
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _grabber(self):
        """A frame-grab function for this thread. Screen captures keep one
        mss handle open here (opening one per grab is too slow to keep up
        with the stream)."""
        region = getattr(self.cap, "region", None)
        if region is None:
            return self.cap.frame, getattr(self.cap, "frame_index", None)
        import cv2
        import mss
        sct = mss.mss()

        def grab():
            return cv2.cvtColor(np.array(sct.grab(region)), cv2.COLOR_BGRA2BGR)
        return grab, None

    def _run(self):
        grab, frame_index = None, None
        last_index = None
        while not self._stop:
            try:
                if grab is None:
                    grab, frame_index = self._grabber()
                frame = grab()
                now = time.time()
                with self._lock:
                    self._latest = frame
                if frame_index is not None:
                    index = frame_index()
                    if index == last_index:
                        time.sleep(0.002)
                        continue
                    last_index = index
                else:
                    time.sleep(0.005)
                native = gb_screen.native(frame)
                with self._lock:
                    self.recorder.add(now, native)
            except Exception as e:      # keep recording; frame() reports it
                self._error = e
                grab = None
                time.sleep(0.1)

    def frame(self):
        end = time.time() + 5.0
        while True:
            with self._lock:
                latest = self._latest
            if latest is not None:
                return latest
            if time.time() > end:
                raise RuntimeError(f"no frames from the capture ({self._error})")
            time.sleep(0.01)

    def clear(self):
        """Forget everything recorded so far (call at each soft reset)."""
        with self._lock:
            self.recorder.clear()

    def analyse(self):
        with self._lock:
            stats = list(self.recorder.stats)
        return shiny_flash.analyse(stats)

    def close(self):
        self._stop = True
