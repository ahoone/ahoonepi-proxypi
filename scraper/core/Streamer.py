import os
import subprocess

from scraper.core.Display import Display

STREAM_FPS = 12
STREAM_QUALITY = 15  # 2=best 31=worst
TIMEOUT_KILL = 6  # seconds


class Streamer:
    process: subprocess.Popen

    def __init__(self, display: Display) -> None:
        command = [
            "ffmpeg",
            "-loglevel",
            "quiet",
            "-f",
            "x11grab",
            "-framerate",
            str(STREAM_FPS),
            "-video_size",
            f"{display.window_size[0]}x{display.window_size[1]}",
            "-i",
            display.display,
            "-f",
            "mjpeg",
            "-q:v",
            str(STREAM_QUALITY),
            "-flush_packets",
            "1",
            "pipe:1",
        ]

        self.process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env={**os.environ, "DISPLAY": display.display},
        )

    def kill(self) -> None:
        self.process.terminate()
        try:
            self.process.wait(timeout=TIMEOUT_KILL)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=TIMEOUT_KILL)
