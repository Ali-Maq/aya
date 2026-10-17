"""Generate local narration and a subtitle file from the reviewed story."""

import concurrent.futures
import json
import subprocess
from pathlib import Path
from typing import NotRequired, TypedDict


class Scene(TypedDict):
    id: str
    seconds: int
    text: str
    rate: NotRequired[int]


class AudioReport(TypedDict):
    scene: str
    audio_seconds: float
    scene_seconds: int


ROOT = Path(__file__).resolve().parent
STORY: list[Scene] = json.loads((ROOT / "story.json").read_text())


def narration(item: tuple[int, Scene]) -> AudioReport:
    index, scene = item
    source = ROOT / ".build" / f"voice-{index}.txt"
    source.write_text(scene["text"])
    aiff = source.with_suffix("aiff")
    wav = ROOT / "public" / f"voice-{index}.wav"
    subprocess.run(
        [
            "say",
            "-v",
            "Samantha",
            "-r",
            str(scene.get("rate", 180)),
            "-f",
            str(source),
            "-o",
            str(aiff),
        ],
        check=True,
    )
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-i",
            str(aiff),
            "-ar",
            "48000",
            "-ac",
            "1",
            str(wav),
        ],
        check=True,
    )
    seconds = float(
        subprocess.check_output(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=nw=1:nk=1",
                str(wav),
            ]
        )
    )
    if seconds >= scene["seconds"] - 0.25:
        raise ValueError(f"Narration does not fit scene {scene['id']}: {seconds}")
    return {
        "scene": scene["id"],
        "audio_seconds": seconds,
        "scene_seconds": scene["seconds"],
    }


def timestamp(seconds: float) -> str:
    milliseconds = round(seconds * 1000)
    hours, milliseconds = divmod(milliseconds, 3_600_000)
    minutes, milliseconds = divmod(milliseconds, 60_000)
    seconds, milliseconds = divmod(milliseconds, 1000)
    return f"{hours:02}:{minutes:02}:{seconds:02},{milliseconds:03}"


if __name__ == "__main__":
    (ROOT / ".build").mkdir(exist_ok=True)
    (ROOT / "public").mkdir(exist_ok=True)
    (ROOT / "output").mkdir(exist_ok=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        report = list(pool.map(narration, enumerate(STORY)))
    (ROOT / ".build" / "audio-report.json").write_text(json.dumps(report, indent=2))
    start = 0
    captions: list[str] = []
    for index, scene in enumerate(STORY):
        captions.append(
            f"{index + 1}\n{timestamp(start)} --> {timestamp(start + scene['seconds'] - 0.2)}\n{scene['text']}\n"
        )
        start += scene["seconds"]
    subtitle_text = "\n".join(captions)
    (ROOT / "captions.srt").write_text(subtitle_text)
    (ROOT / "output" / "AYA-demo.srt").write_text(subtitle_text)
