from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from emulator import list_emulators, send_fix
from routes import Point, playback_samples, read_route, route_length


class RouteTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)

    def route(self, name, source):
        path = Path(self.folder.name) / name
        path.write_text(source, encoding="utf-8")
        return read_route(path)

    def test_imports_txt_gpx_and_kml(self):
        txt = self.route("route.txt", "22.1,114.1\n22.1001 114.1\n")
        gpx = self.route("route.gpx", """<gpx xmlns="http://www.topografix.com/GPX/1/1">
            <trk><trkseg><trkpt lat="22.1" lon="114.1"/><trkpt lat="22.1001" lon="114.1"/></trkseg></trk>
            </gpx>""")
        kml = self.route("route.kml", """<kml xmlns="http://www.opengis.net/kml/2.2">
            <LineString><coordinates>114.1,22.1,0 114.1,22.1001,0</coordinates></LineString></kml>""")
        self.assertEqual(txt, gpx)
        self.assertEqual(txt, kml)

    def test_txt_segments_and_gcj02(self):
        route = self.route("route.txt", """# coord_system=GCJ02
39.9101,116.4011
39.9103,116.4013
PAUSE
39.9111,116.4021
39.9113,116.4023
""")
        self.assertEqual(len(route), 2)
        self.assertAlmostEqual(route[0][0].longitude, 116.39486, places=5)

    def test_gpx_route_metadata_is_ignored(self):
        route = self.route("route.gpx", """<gpx><rte><name>Example</name>
             <rtept lat="22.1" lon="114.1"/><rtept lat="22.1001" lon="114.1"/></rte></gpx>""")
        self.assertEqual(route[0][0], Point(22.1, 114.1))

    def test_invalid_txt_reports_line_number(self):
        with self.assertRaisesRegex(ValueError, "第 2 行"):
            self.route("route.txt", "22.1,114.1\nNaN,22.1\n")

    def test_example_and_playback_timing(self):
        route = read_route(Path(__file__).resolve().parents[1] / "example-route.txt")
        samples = list(playback_samples(route[0], speed_kmh=12))
        self.assertEqual(samples[0], (0, route[0][0]))
        self.assertEqual(samples[-1][1], route[0][-1])
        self.assertAlmostEqual(samples[-1][0], route_length(route) / (12 / 3.6))
        self.assertEqual(sorted(samples, key=lambda item: item[0]), samples)

    def test_playback_stays_near_antimeridian(self):
        start, end = Point(0, 179.999), Point(0, -179.999)
        samples = list(playback_samples((start, end), speed_kmh=100))
        self.assertTrue(all(abs(point.longitude) >= 179.999 - 1e-8 for _, point in samples))


class EmulatorTests(unittest.TestCase):
    @patch("emulator.subprocess.run")
    def test_detects_online_emulators_only(self, run):
        run.return_value = subprocess.CompletedProcess(
            [], 0, "List of devices attached\nemulator-5554\tdevice\nemulator-5556\toffline\n"
            "127.0.0.1:5555\tdevice\n", "",
        )
        self.assertEqual(list_emulators("adb"), ("emulator-5554",))

    @patch("emulator.subprocess.run")
    def test_sends_longitude_first_and_requires_acknowledgment(self, run):
        run.return_value = subprocess.CompletedProcess([], 0, "OK\r\n", "")
        send_fix("adb", "emulator-5554", Point(22.1, 114.1))
        self.assertEqual(run.call_args.args[0],
                         ["adb", "-s", "emulator-5554", "emu", "geo", "fix", "114.1", "22.1"])
        run.return_value = subprocess.CompletedProcess([], 0, "KO: command failed\n", "")
        with self.assertRaisesRegex(RuntimeError, "command failed"):
            send_fix("adb", "emulator-5554", Point(22.1, 114.1))

    @patch("emulator.subprocess.run")
    def test_rejects_non_emulator_selection(self, run):
        with self.assertRaises(ValueError):
            send_fix("adb", "127.0.0.1:5555", Point(22.1, 114.1))
        run.assert_not_called()

    @patch("emulator.subprocess.run", side_effect=FileNotFoundError)
    def test_missing_adb_has_actionable_message(self, _run):
        with self.assertRaisesRegex(RuntimeError, "adb.exe"):
            list_emulators("missing-adb")


if __name__ == "__main__":
    unittest.main()
