"""Load cases.yaml and resolve per-case paths (server layout)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

import yaml

from paths import (
    AWAKEN_DATA,
    AWAKEN_PBL_FUZZY_OUTPUT,
    AWAKEN_WINDOE_OUTPUT,
    CASES_YAML,
    CASE_GALLERY_FIGURES,
    CASE_GALLERY_PBL_FUZZY,
    CASE_GALLERY_WINDOE,
    staged_case_dir,
)

# Approximate CLAMPS site coordinates by campaign (lat °N, lon °E, alt m MSL)
PROJECT_SITES: dict[str, tuple[float, float, float]] = {
    "TRACER": (29.617, -95.75, 15.0),
    "PERiLS2022": (30.15, -92.20, 10.0),
    "PERiLS2023": (30.15, -92.20, 10.0),
    "AWAKEN": (36.3798, -97.5234, 321.0),
    "AWAKEN2023": (36.3798, -97.5234, 321.0),
    "Norman": (35.01, -97.52, 360.0),
    "BLISSFUL": (32.30, -90.85, 80.0),
    "SPLASH": (36.61, -121.64, 50.0),
    "PBLtops": (36.61, -97.49, 318.0),
    "NWCRIL2020": (36.61, -97.49, 318.0),
}

_DEFAULT_SITE = PROJECT_SITES["Norman"]
_SOURCES_CACHE: dict[str, Any] | None = None


@dataclass(frozen=True)
class CaseFiles:
    dlppi: Path
    dlvad: Path
    dlfp: Path
    tropoe: Path


@dataclass
class CaseSpec:
    """One gallery candidate (compatible with uploaded laptop pipeline modules)."""

    id: str
    category: str
    project: str
    platform: str
    case_date: date
    reuse_awaken: bool = False
    source: str = ""
    lat: float = 0.0
    lon: float = 0.0
    alt_m: float = 0.0

    @property
    def case_id(self) -> str:
        return self.id

    @property
    def clamps_root(self) -> Path:
        if self.reuse_awaken:
            return AWAKEN_DATA
        return staged_case_dir(self.id)

    @property
    def windoe_dir(self) -> Path:
        if self.reuse_awaken:
            return AWAKEN_WINDOE_OUTPUT
        return CASE_GALLERY_WINDOE / self.id

    @property
    def pbl_dir(self) -> Path:
        if self.reuse_awaken:
            return AWAKEN_PBL_FUZZY_OUTPUT
        return CASE_GALLERY_PBL_FUZZY / self.id

    @property
    def figure_dir(self) -> Path:
        return CASE_GALLERY_FIGURES / self.id

    @property
    def figure_out(self) -> Path:
        return self.figure_dir / "instrument_template_4panel.png"

    @property
    def windoe_rootname(self) -> str:
        n = self.platform[-1]
        if self.reuse_awaken:
            return f"awaken_clamps{n}.WINDoe.c{n}"
        return f"gallery_clamps{n}.WINDoe.c{n}"

    @property
    def pbl_nc_name(self) -> str:
        return f"{self.case_date.strftime('%Y%m%d')}_{self.platform}fuzzyPBLh.nc"


def platform_from_case_id(case_id: str) -> str:
    if case_id.endswith("_c1"):
        return "C1"
    if case_id.endswith("_c2"):
        return "C2"
    raise ValueError(f"Cannot infer platform from case_id: {case_id}")


def _parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def _load_yaml() -> dict[str, Any]:
    with CASES_YAML.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def _sources() -> dict[str, Any]:
    global _SOURCES_CACHE
    if _SOURCES_CACHE is None:
        raw = _load_yaml()
        _SOURCES_CACHE = raw.get("sources") or {}
    return _SOURCES_CACHE


def get_source(source_key: str) -> dict[str, Any]:
    sources = _sources()
    if source_key not in sources:
        raise KeyError(
            f"Unknown THREDDS source '{source_key}'. "
            "Add a 'sources:' block to cases.yaml or use --skip-download."
        )
    return sources[source_key]


def load_cases(yaml_path: Path | None = None) -> dict[str, CaseSpec]:
    path = yaml_path or CASES_YAML
    with path.open(encoding="utf-8") as f:
        raw: dict[str, Any] = yaml.safe_load(f)
    cases: dict[str, CaseSpec] = {}
    for case_id, spec in raw["cases"].items():
        lat, lon, alt = PROJECT_SITES.get(spec["project"], _DEFAULT_SITE)
        cases[case_id] = CaseSpec(
            id=case_id,
            category=spec["category"],
            project=spec["project"],
            platform=platform_from_case_id(case_id),
            case_date=_parse_date(spec["date"]),
            reuse_awaken=bool(spec.get("reuse_awaken", False)),
            source=spec.get("source", case_id),
            lat=float(spec.get("lat", lat)),
            lon=float(spec.get("lon", lon)),
            alt_m=float(spec.get("alt_m", alt)),
        )
    return cases


def get_case(case_id: str) -> CaseSpec:
    cases = load_cases()
    if case_id not in cases:
        raise KeyError(f"Unknown case_id: {case_id}")
    return cases[case_id]


def _one_file(
    directory: Path,
    pattern: str,
    label: str,
    *,
    prefer_ymd: str | None = None,
) -> Path:
    if not directory.is_dir():
        raise FileNotFoundError(f"Missing {label} directory: {directory}")
    matches = sorted(directory.glob(pattern))
    if not matches:
        raise FileNotFoundError(f"No {label} file matching {pattern} in {directory}")
    if prefer_ymd:
        dated = [p for p in matches if prefer_ymd in p.name]
        if dated:
            return dated[-1]
    return matches[-1]


def find_case_files(case: CaseSpec) -> CaseFiles:
    root = case.clamps_root
    ymd = case.case_date.strftime("%Y%m%d")
    return CaseFiles(
        dlppi=_one_file(root / "dlppi", "*dlppi*", "DL PPI", prefer_ymd=ymd),
        dlvad=_one_file(root / "dlvad", "*dlvad*", "DLVAD", prefer_ymd=ymd),
        dlfp=_one_file(root / "dlfp", "*dlfp*", "DLFP", prefer_ymd=ymd),
        tropoe=_one_file(root / "tropoe", "*", "TROPoe/AERIoe", prefer_ymd=ymd),
    )


def find_windoe_file(case: CaseSpec) -> Path:
    ymd = case.case_date.strftime("%Y%m%d")
    plat = case.platform.lower()
    patterns = [
        f"{case.windoe_rootname}.{ymd}*.nc",
        f"*WINDoe*{plat}*{ymd}*.nc",
        f"*{ymd}*.nc",
    ]
    for pat in patterns:
        matches = sorted(case.windoe_dir.glob(pat))
        if matches:
            return matches[-1]
    raise FileNotFoundError(
        f"No WINDoe output in {case.windoe_dir} for {case.id} ({ymd})"
    )


def find_pbl_file(case: CaseSpec) -> Path:
    path = case.pbl_dir / case.pbl_nc_name
    if path.is_file():
        return path
    matches = sorted(case.pbl_dir.glob(f"*{case.case_date.strftime('%Y%m%d')}*fuzzy*.nc"))
    if matches:
        return matches[-1]
    raise FileNotFoundError(f"No PBL fuzzy output in {case.pbl_dir}")
