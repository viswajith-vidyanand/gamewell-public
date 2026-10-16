"""Read only aggregate result artifacts from the repository results folder."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[1]
RESULTS_DIR = REPO_ROOT / "results"
ALLOWED_SUFFIXES = {".csv", ".json", ".svg", ".md"}


def list_result_files(suffix: str | None = None) -> list[str]:
    """List result artifacts only; never traverse outside results/."""
    files = sorted(
        p.name for p in RESULTS_DIR.iterdir()
        if p.is_file() and p.suffix.lower() in ALLOWED_SUFFIXES
        and (suffix is None or p.suffix.lower() == suffix.lower())
    )
    return files


def _result_path(name: str) -> Path:
    candidate = (RESULTS_DIR / name).resolve()
    if candidate.parent != RESULTS_DIR.resolve() or candidate.suffix.lower() not in ALLOWED_SUFFIXES:
        raise ValueError("Only files directly inside results/ may be loaded.")
    if not candidate.is_file():
        raise FileNotFoundError(name)
    return candidate


def load_csv(name: str) -> pd.DataFrame:
    """Load one results CSV; pandas missing values remain NaN."""
    if Path(name).suffix.lower() != ".csv":
        raise ValueError("Expected a CSV file.")
    return pd.read_csv(_result_path(name), keep_default_na=True)


def load_json(name: str = "headline.json") -> dict[str, Any]:
    if Path(name).suffix.lower() != ".json":
        raise ValueError("Expected a JSON file.")
    with _result_path(name).open(encoding="utf-8") as f:
        return json.load(f)


def load_text(name: str) -> str:
    if Path(name).suffix.lower() not in {".md", ".svg"}:
        raise ValueError("Expected an SVG or Markdown file.")
    return _result_path(name).read_text(encoding="utf-8")


def load_claims() -> dict[str, str]:
    frame = load_csv("CLAIMS_REGISTER.csv")
    return dict(zip(frame["claim_id"].astype(str), frame["exact_wording"].astype(str)))


def load_dictionary() -> pd.DataFrame:
    return load_csv("DATA_DICTIONARY.csv")


def column_descriptions(file_name: str) -> dict[str, str]:
    dictionary = load_dictionary()
    subset = dictionary.loc[dictionary["file"].eq(file_name)]
    return dict(zip(subset["column"].astype(str), subset["definition"].fillna("")))
