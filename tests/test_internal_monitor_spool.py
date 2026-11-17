import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

# The Android service imports PyJNIus, which is not installed on the CI host.
sys.modules.setdefault("jnius", types.SimpleNamespace(autoclass=lambda *_: None))

from services import internal_monitor


class SpoolCheckpointTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.spool = Path(self.temp_dir.name) / "yj64-report.jsonl"
        self.config = {"bridge": {}}

    def write_report(self, report_id):
        with self.spool.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"report_id": report_id}) + "\n")

    def test_checkpoint_survives_service_restart(self):
        self.write_report("first")
        delivered = []
        with patch.object(
            internal_monitor, "send_bridge",
            side_effect=lambda _config, report: delivered.append(report["report_id"]) or True,
        ):
            first_offset = internal_monitor.forward_spool_reports(
                self.config, self.spool, 0
            )
            self.write_report("second")
            # Simulate a new service process whose in-memory offset reset to zero.
            second_offset = internal_monitor.forward_spool_reports(
                self.config, self.spool, 0
            )

        self.assertEqual(delivered, ["first", "second"])
        self.assertGreater(second_offset, first_offset)
        checkpoint = Path(str(self.spool) + ".offset")
        self.assertEqual(int(checkpoint.read_text(encoding="ascii")), second_offset)

    def test_failed_delivery_does_not_advance_checkpoint(self):
        self.write_report("pending")
        with patch.object(internal_monitor, "send_bridge", return_value=False):
            offset = internal_monitor.forward_spool_reports(
                self.config, self.spool, 0
            )
        self.assertEqual(offset, 0)
        self.assertFalse(Path(str(self.spool) + ".offset").exists())

        delivered = []
        with patch.object(
            internal_monitor, "send_bridge",
            side_effect=lambda _config, report: delivered.append(report["report_id"]) or True,
        ):
            internal_monitor.forward_spool_reports(self.config, self.spool, 0)
        self.assertEqual(delivered, ["pending"])

    def test_malformed_line_is_skipped_and_checkpointed(self):
        self.spool.write_text("{not-json}\n", encoding="utf-8")
        with patch.object(internal_monitor, "send_bridge", return_value=True):
            offset = internal_monitor.forward_spool_reports(
                self.config, self.spool, 0
            )
        self.assertEqual(offset, self.spool.stat().st_size)
        self.assertEqual(
            int(Path(str(self.spool) + ".offset").read_text(encoding="ascii")),
            offset,
        )


if __name__ == "__main__":
    unittest.main()
