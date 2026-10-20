import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import desktop_platform
import gs_engine


class PlatformTest(unittest.TestCase):
    def test_data_locations_are_writable_user_locations(self):
        home = Path.home()
        with patch.object(desktop_platform.sys, "platform", "darwin"):
            self.assertEqual(desktop_platform.application_data_dir(), home / "Library/Application Support/PDF简作")
        with patch.object(desktop_platform.sys, "platform", "win32"), patch.dict("os.environ", {"LOCALAPPDATA": str(home / "AppData/Local")}):
            self.assertEqual(desktop_platform.application_data_dir(), home / "AppData/Local/PDF简作")

    def test_finder_receives_path_as_one_argument(self):
        with patch.object(desktop_platform.sys, "platform", "darwin"), patch.object(desktop_platform.subprocess, "Popen") as launch:
            desktop_platform.open_folder(Path(__file__).resolve().parent)
            self.assertEqual(launch.call_args.args[0], ["/usr/bin/open", str(Path(__file__).resolve().parent)])
            self.assertNotIn("shell", launch.call_args.kwargs)

    def test_frozen_engine_comes_from_bundle(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as folder:
            root = Path(folder)
            for system, relative in (("darwin", "lib/libgs.dylib"), ("win32", "bin/gsdll64.dll")):
                expected = root / "ghostscript" / relative
                expected.parent.mkdir(parents=True, exist_ok=True)
                expected.touch()
                with patch.object(gs_engine.sys, "platform", system), patch.object(gs_engine.sys, "_MEIPASS", str(root), create=True):
                    self.assertEqual(gs_engine.engine_path(), expected)
            with patch.object(gs_engine.sys, "platform", "darwin"), patch.object(gs_engine.sys, "_MEIPASS", str(root / "missing"), create=True):
                with self.assertRaises(FileNotFoundError): gs_engine.engine_path()

    def test_mac_builder_refuses_to_fake_a_mac_app_on_windows(self):
        path = Path(__file__).resolve().parent / "packaging/build_macos.py"
        spec = importlib.util.spec_from_file_location("mac_builder", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with patch.object(module.sys, "platform", "win32"):
            with self.assertRaisesRegex(SystemExit, "must be built on a Mac"):
                module.build()


if __name__ == "__main__": unittest.main()
