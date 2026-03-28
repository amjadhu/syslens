"""Tests for syslens/collectors/reboot.py and display.render_reboot()."""

import json
import subprocess
from unittest.mock import MagicMock, patch

import pytest
from rich.console import Console


# ===========================================================================
# _classify()
# ===========================================================================

class TestClassify:

    def test_6005_is_boot(self):
        from syslens.collectors.reboot import _classify
        kind, label, color = _classify(6005, "")
        assert kind == "boot"
        assert "boot" in label.lower()
        assert color == "green"

    def test_6006_is_clean_shutdown(self):
        from syslens.collectors.reboot import _classify
        kind, label, color = _classify(6006, "")
        assert kind == "clean_shutdown"
        assert color == "blue"

    def test_6008_power_loss_with_time_and_date(self):
        from syslens.collectors.reboot import _classify
        msg = "The previous system shutdown at 5:42:21 AM on ?3/?23/?2026 was unexpected."
        kind, label, color = _classify(6008, msg)
        assert kind == "power_loss"
        assert "5:42:21 AM" in label
        assert "3/23/2026" in label
        assert color == "red"

    def test_6008_power_loss_time_only_when_no_date(self):
        from syslens.collectors.reboot import _classify
        msg = "The previous system shutdown at 9:00:00 PM on somegarbage was unexpected."
        kind, label, color = _classify(6008, msg)
        assert kind == "power_loss"
        assert "9:00:00 PM" in label
        assert color == "red"

    def test_6008_no_time_in_message(self):
        from syslens.collectors.reboot import _classify
        kind, label, color = _classify(6008, "The previous system shutdown was unexpected.")
        assert kind == "power_loss"
        assert color == "red"

    def test_41_bugcheck_zero_is_power_loss(self):
        from syslens.collectors.reboot import _classify
        msg = "The system has rebooted without cleanly shutting down first.\nBugcheckCode 0\nBugcheckParameter1 0x0"
        kind, label, color = _classify(41, msg)
        assert kind == "power_loss"
        assert "BugcheckCode 0" in label
        assert color == "red"

    def test_41_nonzero_bugcheck_is_crash(self):
        from syslens.collectors.reboot import _classify
        msg = "The system has rebooted without cleanly shutting down first.\nBugcheckCode 30\n"
        kind, label, color = _classify(41, msg)
        assert kind == "crash"
        assert "0x0000001E" in label or "crash" in label.lower()
        assert color == "red"

    def test_41_no_bugcheck_in_message(self):
        from syslens.collectors.reboot import _classify
        kind, label, color = _classify(41, "The system restarted unexpectedly.")
        assert kind == "unexpected"
        assert color == "red"

    def test_1074_restart_kind(self):
        from syslens.collectors.reboot import _classify
        msg = (
            "The process winlogon.exe has initiated the restart of computer HOST.\n"
            "Reason Code: 0x40030011\nShutdown Type: restart\nComment: \n"
        )
        kind, label, color = _classify(1074, msg)
        assert kind == "restart"
        assert color == "cyan"

    def test_1074_shutdown_kind(self):
        from syslens.collectors.reboot import _classify
        msg = (
            "The process winlogon.exe has initiated the power-off of computer HOST.\n"
            "Reason Code: 0x40030011\nShutdown Type: shutdown\nComment: \n"
        )
        kind, label, color = _classify(1074, msg)
        assert kind == "shutdown"
        assert color == "blue"

    def test_unknown_event_id(self):
        from syslens.collectors.reboot import _classify
        kind, label, color = _classify(9999, "some message")
        assert kind == "unknown"
        assert color == "dim"


# ===========================================================================
# _extract_1074_detail()
# ===========================================================================

class TestExtract1074Detail:

    def test_extracts_comment_field(self):
        from syslens.collectors.reboot import _extract_1074_detail
        msg = "... initiated the restart ...\nReason Code: 0x80040001\nShutdown Type: restart\nComment: Updates\n"
        shutdown_type, reason = _extract_1074_detail(msg)
        assert shutdown_type == "restart"
        assert reason == "Updates"

    def test_extracts_windows_update_from_reason_code(self):
        from syslens.collectors.reboot import _extract_1074_detail
        msg = "... initiated the restart ...\nReason Code: 0x80040001\nShutdown Type: restart\nComment: \n"
        _, reason = _extract_1074_detail(msg)
        assert reason == "Windows Update"

    def test_extracts_from_wuauclt_executable(self):
        from syslens.collectors.reboot import _extract_1074_detail
        msg = "The process wuauclt.exe has initiated the restart of HOST.\nShutdown Type: restart\nComment: \n"
        _, reason = _extract_1074_detail(msg)
        assert reason == "Windows Update"

    def test_extracts_user_initiated_from_winlogon(self):
        from syslens.collectors.reboot import _extract_1074_detail
        msg = "The process winlogon.exe initiated the restart of HOST.\nShutdown Type: restart\nComment: \n"
        _, reason = _extract_1074_detail(msg)
        assert reason == "User initiated"

    def test_returns_empty_reason_when_nothing_matches(self):
        from syslens.collectors.reboot import _extract_1074_detail
        msg = "The process xyz.exe has initiated the restart.\nShutdown Type: restart\nComment: \n"
        _, reason = _extract_1074_detail(msg)
        assert reason == ""

    def test_shutdown_type_detected_as_shutdown(self):
        from syslens.collectors.reboot import _extract_1074_detail
        msg = "The process xyz.exe has initiated the power-off."
        shutdown_type, _ = _extract_1074_detail(msg)
        assert shutdown_type == "shutdown"


# ===========================================================================
# collect() — mocked subprocess
# ===========================================================================

class TestCollect:

    def _fake_ps_events(self, events):
        """Return a mock subprocess result whose stdout is the JSON of events."""
        mock = MagicMock()
        mock.stdout = json.dumps(events)
        return mock

    def _base_event(self, event_id, msg="", provider="EventLog", time="2026-03-27 10:00:00"):
        return {"Id": event_id, "Message": msg, "ProviderName": provider, "Time": time}

    def test_collect_returns_required_keys(self):
        from syslens.collectors import reboot
        events = [self._base_event(6005)]
        with patch("platform.system", return_value="Windows"):
            with patch("subprocess.run", return_value=self._fake_ps_events(events)):
                result = reboot.collect()
        for key in ("platform", "last_boot", "uptime", "last_reason",
                    "last_kind", "last_color", "timeline", "error"):
            assert key in result, f"Missing key: {key}"

    def test_collect_platform_stored(self):
        from syslens.collectors import reboot
        with patch("platform.system", return_value="Windows"):
            with patch("subprocess.run", return_value=self._fake_ps_events([])):
                result = reboot.collect()
        assert result["platform"] == "Windows"

    def test_timeline_contains_classified_events(self):
        from syslens.collectors import reboot
        events = [
            self._base_event(6005, time="2026-03-27 10:00:05"),
            self._base_event(6006, time="2026-03-27 09:59:55"),
        ]
        with patch("platform.system", return_value="Windows"):
            with patch("subprocess.run", return_value=self._fake_ps_events(events)):
                result = reboot.collect()
        kinds = [e["kind"] for e in result["timeline"]]
        assert "boot" in kinds
        assert "clean_shutdown" in kinds

    def test_last_reason_identified_from_pre_boot_event(self):
        from syslens.collectors import reboot
        # boot event followed by a clean_shutdown event (chronologically older)
        events = [
            self._base_event(6005, time="2026-03-27 10:00:05"),
            self._base_event(6006, time="2026-03-27 09:59:55"),
        ]
        with patch("platform.system", return_value="Windows"):
            with patch("subprocess.run", return_value=self._fake_ps_events(events)):
                result = reboot.collect()
        assert result["last_kind"] == "clean_shutdown"

    def test_power_loss_identified_correctly(self):
        from syslens.collectors import reboot
        msg_6008 = "The previous system shutdown at 9:00:00 PM on 3/26/2026 was unexpected."
        events = [
            self._base_event(6005, time="2026-03-27 10:00:05"),
            self._base_event(6008, msg_6008, time="2026-03-27 10:00:06"),
        ]
        with patch("platform.system", return_value="Windows"):
            with patch("subprocess.run", return_value=self._fake_ps_events(events)):
                result = reboot.collect()
        assert result["last_kind"] == "power_loss"
        assert "9:00:00 PM" in result["last_reason"]

    def test_error_returned_on_timeout(self):
        from syslens.collectors import reboot
        with patch("platform.system", return_value="Windows"):
            with patch("subprocess.run",
                       side_effect=subprocess.TimeoutExpired(["powershell.exe"], 20)):
                result = reboot.collect()
        assert result["error"] is not None
        assert "timed out" in result["error"].lower()
        assert result["timeline"] == []

    def test_empty_event_list_gives_unknown_reason(self):
        from syslens.collectors import reboot
        with patch("platform.system", return_value="Windows"):
            with patch("subprocess.run", return_value=self._fake_ps_events([])):
                result = reboot.collect()
        assert result["last_kind"] == "unknown"
        assert result["timeline"] == []

    def test_unsupported_platform_returns_error(self):
        from syslens.collectors import reboot
        with patch("platform.system", return_value="Linux"):
            result = reboot.collect()
        assert result["error"] is not None
        assert "not supported" in result["error"].lower()
        assert result["timeline"] == []

    def test_single_event_dict_wrapped_in_list(self):
        """PowerShell returns a bare object (not array) when there's only one event."""
        from syslens.collectors import reboot
        single = self._base_event(6005, time="2026-03-27 10:00:00")
        mock_result = MagicMock()
        mock_result.stdout = json.dumps(single)  # bare dict, not list
        with patch("platform.system", return_value="Windows"):
            with patch("subprocess.run", return_value=mock_result):
                result = reboot.collect()
        assert len(result["timeline"]) == 1

    def test_powershell_not_found_returns_error(self):
        from syslens.collectors import reboot
        with patch("platform.system", return_value="Windows"):
            with patch("subprocess.run", side_effect=FileNotFoundError):
                result = reboot.collect()
        assert result["error"] is not None

    def test_uptime_format_days(self):
        from syslens.collectors import reboot
        from datetime import datetime, timedelta
        import psutil
        boot_ts = (datetime.now() - timedelta(days=3, hours=2, minutes=15)).timestamp()
        with patch("platform.system", return_value="Windows"):
            with patch("subprocess.run", return_value=self._fake_ps_events([])):
                with patch("psutil.boot_time", return_value=boot_ts):
                    result = reboot.collect()
        assert result["uptime"].startswith("3d")

    def test_uptime_format_hours(self):
        from syslens.collectors import reboot
        from datetime import datetime, timedelta
        boot_ts = (datetime.now() - timedelta(hours=5, minutes=30)).timestamp()
        with patch("platform.system", return_value="Windows"):
            with patch("subprocess.run", return_value=self._fake_ps_events([])):
                with patch("psutil.boot_time", return_value=boot_ts):
                    result = reboot.collect()
        assert result["uptime"].startswith("5h")

    def test_uptime_format_minutes_only(self):
        from syslens.collectors import reboot
        from datetime import datetime, timedelta
        boot_ts = (datetime.now() - timedelta(minutes=45)).timestamp()
        with patch("platform.system", return_value="Windows"):
            with patch("subprocess.run", return_value=self._fake_ps_events([])):
                with patch("psutil.boot_time", return_value=boot_ts):
                    result = reboot.collect()
        assert result["uptime"].endswith("m")
        assert "h" not in result["uptime"]


# ===========================================================================
# display.render_reboot()
# ===========================================================================

class TestRenderReboot:
    """Tests for the Rich renderer — captures output via record=True."""

    def _render(self, data):
        from syslens import display
        c = Console(record=True, width=120)
        original = display.console
        display.console = c
        try:
            display.render_reboot(data)
        finally:
            display.console = original
        return c.export_text()

    def _base_data(self, **overrides):
        data = {
            "platform":    "Windows",
            "last_boot":   "2026-03-27 21:26:19",
            "uptime":      "3h 0m",
            "last_reason": "Clean restart — Windows Update",
            "last_kind":   "restart",
            "last_color":  "cyan",
            "timeline":    [],
            "error":       None,
        }
        data.update(overrides)
        return data

    def test_renders_without_raising(self):
        self._render(self._base_data())

    def test_shows_last_boot_time(self):
        out = self._render(self._base_data())
        assert "2026-03-27 21:26:19" in out

    def test_shows_uptime(self):
        out = self._render(self._base_data())
        assert "3h 0m" in out

    def test_shows_restart_reason(self):
        out = self._render(self._base_data())
        assert "Windows Update" in out

    def test_shows_explanation_for_power_loss(self):
        out = self._render(self._base_data(
            last_kind="power_loss",
            last_reason="Unexpected shutdown — power loss, freeze, or hard reset",
            last_color="red",
        ))
        assert "power" in out.lower()

    def test_shows_explanation_for_crash(self):
        out = self._render(self._base_data(
            last_kind="crash",
            last_reason="System crash (BSOD) — stop code 0x0000001E",
            last_color="red",
        ))
        assert "crash" in out.lower() or "BSOD" in out

    def test_shows_error_note_when_present(self):
        out = self._render(self._base_data(error="powershell.exe not found"))
        assert "powershell.exe not found" in out

    def test_no_error_note_when_none(self):
        out = self._render(self._base_data(error=None))
        assert "Note:" not in out

    def test_renders_timeline_events(self):
        timeline = [
            {"time": "2026-03-27 21:26:41", "event_id": 6005,
             "kind": "boot", "label": "System started (boot)",
             "color": "green", "provider": "EventLog"},
            {"time": "2026-03-27 21:26:40", "event_id": 6006,
             "kind": "clean_shutdown", "label": "System shut down cleanly",
             "color": "blue", "provider": "EventLog"},
        ]
        out = self._render(self._base_data(timeline=timeline))
        assert "System started (boot)" in out
        assert "System shut down cleanly" in out

    def test_empty_timeline_shows_fallback_message(self):
        out = self._render(self._base_data(timeline=[]))
        assert "No reboot-related events" in out

    def test_long_label_truncated_in_table(self):
        """Labels over 58 chars must not crash or overflow awkwardly."""
        long_label = "X" * 80
        timeline = [
            {"time": "2026-03-27 21:26:41", "event_id": 6005,
             "kind": "boot", "label": long_label,
             "color": "green", "provider": "EventLog"},
        ]
        # Should not raise
        self._render(self._base_data(timeline=timeline))

    @pytest.mark.parametrize("kind,expected_text", [
        ("boot",           "BOOT"),
        ("restart",        "RESTART"),
        ("shutdown",       "SHUTDOWN"),
        ("clean_shutdown", "SHUTDOWN"),
        ("power_loss",     "POWER LOSS"),
        ("crash",          "CRASH"),
        ("unexpected",     "UNEXPECTED"),
        ("unknown",        "?"),
    ])
    def test_event_kind_label_in_output(self, kind, expected_text):
        timeline = [
            {"time": "2026-03-27 10:00:00", "event_id": 0,
             "kind": kind, "label": "some label",
             "color": "white", "provider": "Test"},
        ]
        out = self._render(self._base_data(timeline=timeline))
        assert expected_text in out


# ===========================================================================
# main.py --reboot flag integration (Typer test client)
# ===========================================================================

class TestMainRebootFlag:

    def _reboot_data(self):
        return {
            "platform":    "Windows",
            "last_boot":   "2026-03-27 21:26:19",
            "uptime":      "3h 0m",
            "last_reason": "Clean restart — Windows Update",
            "last_kind":   "restart",
            "last_color":  "cyan",
            "timeline":    [],
            "error":       None,
        }

    def test_reboot_flag_calls_collect(self):
        from typer.testing import CliRunner
        from syslens.main import app
        runner = CliRunner()
        data = self._reboot_data()
        with patch("syslens.collectors.reboot.collect", return_value=data) as mock_collect:
            with patch("syslens.display.render_reboot"):
                result = runner.invoke(app, ["--reboot"])
        mock_collect.assert_called_once()
        assert result.exit_code == 0

    def test_reboot_json_produces_valid_json(self):
        import json
        from typer.testing import CliRunner
        from syslens.main import app
        runner = CliRunner()
        data = self._reboot_data()
        with patch("syslens.collectors.reboot.collect", return_value=data):
            result = runner.invoke(app, ["--reboot", "--json"])
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["platform"] == "Windows"
        assert parsed["last_kind"] == "restart"

    def test_reboot_does_not_invoke_cpu_collector(self):
        from typer.testing import CliRunner
        from syslens.main import app
        runner = CliRunner()
        data = self._reboot_data()
        with patch("syslens.collectors.reboot.collect", return_value=data):
            with patch("syslens.display.render_reboot"):
                with patch("syslens.collectors.cpu.collect") as mock_cpu:
                    result = runner.invoke(app, ["--reboot"])
        mock_cpu.assert_not_called()
        assert result.exit_code == 0

    def test_short_flag_r_works(self):
        from typer.testing import CliRunner
        from syslens.main import app
        runner = CliRunner()
        data = self._reboot_data()
        with patch("syslens.collectors.reboot.collect", return_value=data) as mock_collect:
            with patch("syslens.display.render_reboot"):
                result = runner.invoke(app, ["-r"])
        mock_collect.assert_called_once()
        assert result.exit_code == 0
