"""Demo neighborhood bounds and labels (An Narjis District, Riyadh POC)."""

from __future__ import annotations

NEIGHBORHOOD_POLYGON: list[list[float]] = [
    [24.82991436680011, 46.66972979804959],
    [24.833810953932122, 46.6791362811475],
    [24.826761313414863, 46.682807103819854],
    [24.822775263119926, 46.673302295114645],
]

MIN_LAT = 24.822775263119926
MAX_LAT = 24.833810953932122
MIN_LNG = 46.66972979804959
MAX_LNG = 46.682807103819854

NEIGHBORHOOD_CENTER: tuple[float, float] = (
    sum(point[0] for point in NEIGHBORHOOD_POLYGON) / len(NEIGHBORHOOD_POLYGON),
    sum(point[1] for point in NEIGHBORHOOD_POLYGON) / len(NEIGHBORHOOD_POLYGON),
)

DEMO_NAME_EN = "An Narjis District, Riyadh"
DEMO_NAME_AR = "حي النرجس، الرياض"


def is_point_inside_demo_area(latitude: float, longitude: float) -> bool:
    return MIN_LAT <= latitude <= MAX_LAT and MIN_LNG <= longitude <= MAX_LNG


def clamp_to_demo_bounds(lat: float, lon: float) -> tuple[float, float]:
    return min(MAX_LAT, max(MIN_LAT, lat)), min(MAX_LNG, max(MIN_LNG, lon))


def neighborhood_context(is_inside: bool) -> dict:
    return {
        "name": DEMO_NAME_EN,
        "name_ar": DEMO_NAME_AR,
        "is_inside_demo_area": is_inside,
        "boundary": NEIGHBORHOOD_POLYGON,
    }
