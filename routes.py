"""Import and sample routes for an Android Emulator test session."""

from dataclasses import dataclass
from math import asin, cos, isfinite, radians, sin, sqrt
from pathlib import Path
import re
from xml.etree import ElementTree

from coordinate_transform import gcj2wgs_exact


@dataclass(frozen=True)
class Point:
    latitude: float
    longitude: float

    def __post_init__(self):
        if not (-90 <= self.latitude <= 90 and -180 <= self.longitude <= 180):
            raise ValueError("路线中有无效的经纬度。")


def distance(a, b):
    lat_a, lat_b = radians(a.latitude), radians(b.latitude)
    dlon = radians(b.longitude - a.longitude)
    h = sin((lat_b - lat_a) / 2) ** 2 + cos(lat_a) * cos(lat_b) * sin(dlon / 2) ** 2
    return 12_742_000 * asin(sqrt(max(0, min(1, h))))


def read_route(path):
    path = Path(path)
    if path.stat().st_size > 20_000_000:
        raise ValueError("路线文件超过 20 MB。")
    suffix = path.suffix.lower()
    if suffix == ".txt":
        segments = [[]]
        coordinate_system = "WGS84"
        for number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
            line = line.strip()
            if line.lower().startswith("# coord_system="):
                coordinate_system = line.split("=", 1)[1].strip().upper().replace("-", "")
            elif line and not line.startswith("#"):
                if line.upper() == "PAUSE":
                    segments.append([])
                else:
                    try:
                        lat, lon, *_ = re.split(r"[,\s]+", line)
                        point = Point(float(lat), float(lon))
                    except ValueError:
                        raise ValueError(f"TXT 第 {number} 行的经纬度无效。") from None
                    segments[-1].append(point)
        if coordinate_system == "GCJ02":
            segments = [[Point(*gcj2wgs_exact(p.latitude, p.longitude)) for p in s] for s in segments]
        elif coordinate_system != "WGS84":
            raise ValueError("TXT 坐标系须为 WGS84 或 GCJ02。")
    elif suffix in {".gpx", ".kml"}:
        root = ElementTree.fromstring(path.read_bytes())
        for element in root.iter():
            element.tag = element.tag.rsplit("}", 1)[-1]
        if suffix == ".gpx":
            segments = []
            for group in root.iter():
                if group.tag in {"trkseg", "rte"}:
                    segments.append([Point(float(p.get("lat", "nan")), float(p.get("lon", "nan")))
                                     for p in group if p.tag in {"trkpt", "rtept"}])
        else:
            segments = []
            for group in root.iter("LineString"):
                points = []
                for coordinate in group.findtext("coordinates", "").split():
                    lon, lat, *_ = coordinate.split(",")
                    points.append(Point(float(lat), float(lon)))
                segments.append(points)
    else:
        raise ValueError("请选择 TXT、GPX 或 KML 路线。")

    segments = [tuple(segment) for segment in segments if segment]
    if not segments or any(len(segment) < 2 for segment in segments):
        raise ValueError("每段路线至少需要两个坐标。")
    if not route_length(segments):
        raise ValueError("路线长度必须大于零。")
    return tuple(segments)


def route_length(segments):
    return sum(distance(a, b) for s in segments for a, b in zip(s, s[1:]))


def playback_samples(segment, speed_kmh, interval=1):
    """Yield (deadline in seconds, point) for a fixed-speed test route."""
    if not isfinite(speed_kmh) or not 0.1 <= speed_kmh <= 100:
        raise ValueError("速度须介于 0.1 和 100 km/h 之间。")
    if not isfinite(interval) or interval < 0.1:
        raise ValueError("更新间隔不得少于 0.1 秒。")
    yield 0, segment[0]
    elapsed, next_sample = 0, interval
    for a, b in zip(segment, segment[1:]):
        duration = distance(a, b) / (speed_kmh / 3.6)
        end = elapsed + duration
        longitude_delta = (b.longitude - a.longitude + 180) % 360 - 180
        while next_sample < end:
            fraction = (next_sample - elapsed) / duration
            lat = a.latitude + fraction * (b.latitude - a.latitude)
            lon = (a.longitude + fraction * longitude_delta + 180) % 360 - 180
            yield next_sample, Point(lat, lon)
            next_sample += interval
        elapsed = end
    yield elapsed, segment[-1]
