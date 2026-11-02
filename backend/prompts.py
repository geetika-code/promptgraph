"""Every prompt the tool itself sends to a model lives as a plain text file in backend/prompts/."""
from functools import lru_cache
from pathlib import Path
from string import Template

DIR = Path(__file__).resolve().parent / "prompts"


@lru_cache(maxsize=None)
def _raw(name: str) -> str:
    return (DIR / f"{name}.md").read_text().strip("\n")


def render(name: str, **values) -> str:
    """Fill $placeholders in prompts/<name>.md. Unknown placeholders are left untouched."""
    return Template(_raw(name)).safe_substitute(**values)
