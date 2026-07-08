import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.main import create_app  # noqa: E402


def build_openapi() -> dict:
    return create_app().openapi()


if __name__ == "__main__":
    out = pathlib.Path(__file__).resolve().parents[2] / "openapi.json"
    out.write_text(json.dumps(build_openapi(), indent=2), encoding="utf-8")
    print(f"Wrote {out}")
