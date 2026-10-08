"""FastAPI application loader — body in _app_part1/2."""
from pathlib import Path
_p = Path(__file__).resolve().parent
_src = (_p / "_app_part1.py").read_text(encoding="utf-8") + (_p / "_app_part2.py").read_text(encoding="utf-8")
exec(compile(_src, str(_p / "app.py"), "exec"), globals())
