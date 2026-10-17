"""Prepare the pinned reference and a real GitHub dataset for REA replay."""

import shutil
import urllib.request

from .core import ROOT, STATE, save, sha
from .profiles import SOURCE_COMMIT, SOURCE_PATH, SOURCE_SHA
from .sql_runtime import records


def main() -> None:
    destination = STATE / "reference/fireworks-sql"
    destination.mkdir(parents=True, exist_ok=True)
    artifacts = {
        "sql_tools.py": (SOURCE_PATH, SOURCE_SHA),
        "sql_reward.py": (
            SOURCE_PATH.replace("sql_tools.py", "sql_reward.py"),
            "1d77ba8562a2649de7e49071401c433956494e914c311136707201a175a245a9",
        ),
        "LICENSE": ("LICENSE", None),
    }
    for name, (path, digest) in artifacts.items():
        url = f"https://raw.githubusercontent.com/fw-ai/cookbook/{SOURCE_COMMIT}/{path}"
        with urllib.request.urlopen(url, timeout=30) as response:  # noqa: S310 — fixed GitHub repository and revision
            content = response.read(200_000)
        if digest and sha(content) != digest:
            raise RuntimeError("Reference digest mismatch: " + name)
        (destination / name).write_bytes(content)
    shutil.copyfile(ROOT / "reference/fireworks_sql_probe.py", destination / "probe.py")
    save(destination / "repositories.json", records())
    print("Pinned Fireworks source and live GitHub snapshot prepared for the REA mount")


if __name__ == "__main__":
    main()
