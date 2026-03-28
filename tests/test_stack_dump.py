"""Tests for syslens/collectors/stack_dump.py and display.render_dump()."""

import os
import sys
import types
from unittest.mock import MagicMock, patch, call

import pytest
from rich.console import Console

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_proc(pid=1234, name="notepad.exe", status="running",
               exe=r"C:\Windows\notepad.exe", cmdline=None,
               username="DESKTOP\\user", num_threads=2):
    """Return a mock psutil.Process with common attributes."""
    proc = MagicMock()
    proc.pid = pid
    proc.name.return_value = name
    proc.status.return_value = status
    proc.exe.return_value = exe
    proc.cmdline.return_value = (cmdline or ["notepad.exe"])
    proc.username.return_value = username
    proc.num_threads.return_value = num_threads
    return proc


# ===========================================================================
# _safe()
# ===========================================================================

class TestSafe:
    def test_returns_value_on_success(self):
        from syslens.collectors.stack_dump import _safe
        assert _safe(lambda: 42) == 42

    def test_returns_none_on_access_denied(self):
        import psutil
        from syslens.collectors.stack_dump import _safe
        assert _safe(lambda: (_ for _ in ()).throw(psutil.AccessDenied(0))) is None

    def test_returns_none_on_no_such_process(self):
        import psutil
        from syslens.collectors.stack_dump import _safe
        assert _safe(lambda: (_ for _ in ()).throw(psutil.NoSuchProcess(0))) is None

    def test_returns_none_on_oserror(self):
        from syslens.collectors.stack_dump import _safe
        assert _safe(lambda: (_ for _ in ()).throw(OSError("nope"))) is None


# ===========================================================================
# _find_process()
# ===========================================================================

class TestFindProcess:

    def test_finds_by_pid_when_numeric(self):
        from syslens.collectors.stack_dump import _find_process
        import psutil
        mock_proc = _make_proc(pid=999)
        with patch("psutil.Process", return_value=mock_proc) as mock_cls:
            result = _find_process("999")
        mock_cls.assert_called_once_with(999)
        assert result is mock_proc

    def test_returns_none_for_nonexistent_pid(self):
        from syslens.collectors.stack_dump import _find_process
        import psutil
        with patch("psutil.Process", side_effect=psutil.NoSuchProcess(99999)):
            result = _find_process("99999")
        assert result is None

    def test_finds_by_exact_name_case_insensitive(self):
        from syslens.collectors.stack_dump import _find_process
        proc_a = MagicMock(); proc_a.info = {"name": "Notepad.exe"}
        proc_b = MagicMock(); proc_b.info = {"name": "chrome.exe"}
        with patch("psutil.process_iter", return_value=[proc_a, proc_b]):
            result = _find_process("notepad.exe")
        assert result is proc_a

    def test_exact_name_match_preferred_over_partial(self):
        from syslens.collectors.stack_dump import _find_process
        exact = MagicMock(); exact.info = {"name": "python.exe"}
        partial = MagicMock(); partial.info = {"name": "pythonw.exe"}
        # process_iter is called twice (exact then partial), return same list both times
        with patch("psutil.process_iter", return_value=[exact, partial]):
            result = _find_process("python.exe")
        assert result is exact

    def test_falls_back_to_partial_match(self):
        from syslens.collectors.stack_dump import _find_process
        proc = MagicMock(); proc.info = {"name": "pythonw.exe"}
        # First call (exact) returns nothing; second call (partial) returns proc
        with patch("psutil.process_iter", side_effect=[[], [proc]]):
            result = _find_process("python")
        assert result is proc

    def test_returns_none_when_no_match(self):
        from syslens.collectors.stack_dump import _find_process
        with patch("psutil.process_iter", return_value=[]):
            result = _find_process("nonexistent_xyz")
        assert result is None

    def test_handles_none_process_name(self):
        from syslens.collectors.stack_dump import _find_process
        proc = MagicMock(); proc.info = {"name": None}
        with patch("psutil.process_iter", return_value=[proc]):
            result = _find_process("anything")
        assert result is None

    def test_integer_target_treated_as_pid(self):
        from syslens.collectors.stack_dump import _find_process
        import psutil
        mock_proc = _make_proc(pid=42)
        with patch("psutil.Process", return_value=mock_proc):
            result = _find_process(42)
        assert result is mock_proc


# ===========================================================================
# _run()
# ===========================================================================

class TestRun:
    def test_returns_stripped_stdout(self):
        from syslens.collectors.stack_dump import _run
        mock_result = MagicMock()
        mock_result.stdout = "  hello world  \n"
        with patch("subprocess.run", return_value=mock_result):
            assert _run(["echo", "hello"]) == "hello world"

    def test_returns_empty_on_timeout(self):
        import subprocess
        from syslens.collectors.stack_dump import _run
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(["x"], 5)):
            assert _run(["x"]) == ""

    def test_returns_empty_when_command_not_found(self):
        from syslens.collectors.stack_dump import _run
        with patch("subprocess.run", side_effect=FileNotFoundError):
            assert _run(["notacommand"]) == ""

    def test_returns_empty_on_oserror(self):
        from syslens.collectors.stack_dump import _run
        with patch("subprocess.run", side_effect=OSError):
            assert _run(["x"]) == ""

    def test_returns_empty_on_permission_error(self):
        from syslens.collectors.stack_dump import _run
        with patch("subprocess.run", side_effect=PermissionError):
            assert _run(["x"]) == ""

    def test_returns_empty_when_stdout_none(self):
        from syslens.collectors.stack_dump import _run
        mock_result = MagicMock()
        mock_result.stdout = None
        with patch("subprocess.run", return_value=mock_result):
            assert _run(["x"]) == ""


# ===========================================================================
# _parse_pyspy()
# ===========================================================================

class TestParsePyspy:
    SAMPLE = """\
Thread 0x7f1 (idle)
    _run at /usr/lib/python3.11/threading.py:946
    run at /usr/lib/python3.11/threading.py:870
Thread 0x7f2 (active)
    do_work at myapp.py:12
"""

    def test_parses_two_threads(self):
        from syslens.collectors.stack_dump import _parse_pyspy
        result = _parse_pyspy(self.SAMPLE)
        assert len(result) == 2

    def test_thread_header_captured(self):
        from syslens.collectors.stack_dump import _parse_pyspy
        result = _parse_pyspy(self.SAMPLE)
        assert result[0]["header"] == "Thread 0x7f1 (idle)"

    def test_frames_captured_correctly(self):
        from syslens.collectors.stack_dump import _parse_pyspy
        result = _parse_pyspy(self.SAMPLE)
        assert "_run at /usr/lib/python3.11/threading.py:946" in result[0]["frames"]
        assert "run at /usr/lib/python3.11/threading.py:870" in result[0]["frames"]

    def test_empty_output_returns_empty_list(self):
        from syslens.collectors.stack_dump import _parse_pyspy
        assert _parse_pyspy("") == []

    def test_single_thread_no_trailing_newline(self):
        from syslens.collectors.stack_dump import _parse_pyspy
        result = _parse_pyspy("Thread 0x1 (running)\n    some_frame at file.py:1")
        assert len(result) == 1
        assert result[0]["frames"] == ["some_frame at file.py:1"]


# ===========================================================================
# _parse_gdb()
# ===========================================================================

class TestParseGdb:
    SAMPLE = """\
Thread 1 (Thread 0x7f (LWP 123)):
#0  0x00007f in nanosleep ()
#1  0x00007e in sleep ()
Thread 2 (Thread 0x7e (LWP 124)):
#0  0x00007d in poll ()
"""

    def test_parses_two_threads(self):
        from syslens.collectors.stack_dump import _parse_gdb
        result = _parse_gdb(self.SAMPLE)
        assert len(result) == 2

    def test_frame_lines_start_with_hash(self):
        from syslens.collectors.stack_dump import _parse_gdb
        result = _parse_gdb(self.SAMPLE)
        for frame in result[0]["frames"]:
            assert frame.startswith("#")

    def test_empty_output_returns_empty_list(self):
        from syslens.collectors.stack_dump import _parse_gdb
        assert _parse_gdb("") == []


# ===========================================================================
# _parse_cdb()
# ===========================================================================

class TestParseCdb:
    SAMPLE = """\
   0  Id: 1a2c.1a30 Suspend: 1 Teb: 000000ae`b4fa8000 Unfrozen
      RetAddr           : Args to Child
00000001`0000beef : ntdll!NtWaitForSingleObject+0x14
   1  Id: 1a2c.2210 Suspend: 1 Teb: 000000ae`b4fac000 Unfrozen
      Child-SP          : RetAddr
"""

    def test_parses_two_threads(self):
        from syslens.collectors.stack_dump import _parse_cdb
        result = _parse_cdb(self.SAMPLE)
        assert len(result) == 2

    def test_header_contains_id(self):
        from syslens.collectors.stack_dump import _parse_cdb
        result = _parse_cdb(self.SAMPLE)
        assert "Id:" in result[0]["header"]

    def test_empty_output_returns_empty_list(self):
        from syslens.collectors.stack_dump import _parse_cdb
        assert _parse_cdb("") == []


# ===========================================================================
# _parse_lldb()
# ===========================================================================

class TestParseLldb:
    SAMPLE = """\
* thread #1, stop reason = signal SIGSTOP
  * frame #0: 0x00007fff libsystem_kernel.dylib`mach_msg_trap + 8
    frame #1: 0x00007fff libsystem_kernel.dylib`mach_msg + 76
  thread #2: tid = 0x12
    frame #0: 0x00007fff libsystem_kernel.dylib`__psynch_cvwait + 8
"""

    def test_parses_two_threads(self):
        from syslens.collectors.stack_dump import _parse_lldb
        result = _parse_lldb(self.SAMPLE)
        assert len(result) == 2

    def test_frames_captured(self):
        from syslens.collectors.stack_dump import _parse_lldb
        result = _parse_lldb(self.SAMPLE)
        assert len(result[0]["frames"]) == 2

    def test_empty_output_returns_empty_list(self):
        from syslens.collectors.stack_dump import _parse_lldb
        assert _parse_lldb("") == []


# ===========================================================================
# _try_pyspy()
# ===========================================================================

class TestTryPyspy:
    def test_returns_dict_on_valid_output(self):
        from syslens.collectors.stack_dump import _try_pyspy
        out = "Thread 0x1 (running)\n    frame at file.py:1\n"
        with patch("syslens.collectors.stack_dump._run", return_value=out):
            result = _try_pyspy(123)
        assert result is not None
        assert result["method"] == "py-spy"
        assert "threads" in result
        assert "raw" in result

    def test_returns_none_when_output_empty(self):
        from syslens.collectors.stack_dump import _try_pyspy
        with patch("syslens.collectors.stack_dump._run", return_value=""):
            assert _try_pyspy(123) is None

    def test_returns_none_when_output_lacks_thread_marker(self):
        from syslens.collectors.stack_dump import _try_pyspy
        with patch("syslens.collectors.stack_dump._run", return_value="some garbage output"):
            assert _try_pyspy(123) is None

    def test_passes_correct_pid_to_run(self):
        from syslens.collectors.stack_dump import _try_pyspy
        with patch("syslens.collectors.stack_dump._run", return_value="") as mock_run:
            _try_pyspy(5678)
        cmd = mock_run.call_args[0][0]
        assert "5678" in cmd


# ===========================================================================
# _try_gdb()
# ===========================================================================

class TestTryGdb:
    def test_returns_dict_on_valid_output(self):
        from syslens.collectors.stack_dump import _try_gdb
        out = "Thread 1 (Thread 0x1 (LWP 1)):\n#0  0xdeadbeef in func ()\n"
        with patch("syslens.collectors.stack_dump._run", return_value=out):
            result = _try_gdb(123)
        assert result is not None
        assert result["method"] == "gdb"

    def test_returns_none_when_no_thread_marker(self):
        from syslens.collectors.stack_dump import _try_gdb
        with patch("syslens.collectors.stack_dump._run", return_value="no useful output"):
            assert _try_gdb(123) is None

    def test_returns_none_on_empty_output(self):
        from syslens.collectors.stack_dump import _try_gdb
        with patch("syslens.collectors.stack_dump._run", return_value=""):
            assert _try_gdb(123) is None


# ===========================================================================
# _try_lldb()
# ===========================================================================

class TestTryLldb:
    def test_returns_dict_on_valid_output(self):
        from syslens.collectors.stack_dump import _try_lldb
        out = "* thread #1:\n  * frame #0: 0xdeadbeef libfoo`bar\n"
        with patch("syslens.collectors.stack_dump._run", return_value=out):
            result = _try_lldb(123)
        assert result is not None
        assert result["method"] == "lldb"

    def test_returns_none_when_no_frame_marker(self):
        from syslens.collectors.stack_dump import _try_lldb
        with patch("syslens.collectors.stack_dump._run", return_value="no output"):
            assert _try_lldb(123) is None


# ===========================================================================
# _try_cdb()
# ===========================================================================

class TestTryCdb:
    def test_returns_none_when_cdb_not_found(self):
        from syslens.collectors.stack_dump import _try_cdb
        with patch("syslens.collectors.stack_dump._find_cdb", return_value=None):
            assert _try_cdb(123) is None

    def test_returns_dict_when_cdb_present_and_output_valid(self):
        from syslens.collectors.stack_dump import _try_cdb
        cdb_out = "   0  Id: abc.def Suspend: 1\n   RetAddr  :  Child-SP\n"
        with patch("syslens.collectors.stack_dump._find_cdb", return_value=r"C:\cdb.exe"):
            with patch("syslens.collectors.stack_dump._run", return_value=cdb_out):
                result = _try_cdb(123)
        assert result is not None
        assert result["method"] == "cdb"

    def test_returns_none_when_output_lacks_cdb_markers(self):
        from syslens.collectors.stack_dump import _try_cdb
        with patch("syslens.collectors.stack_dump._find_cdb", return_value=r"C:\cdb.exe"):
            with patch("syslens.collectors.stack_dump._run", return_value="useless output"):
                assert _try_cdb(123) is None


# ===========================================================================
# _find_cdb()
# ===========================================================================

class TestFindCdb:
    def test_returns_none_when_no_dirs_exist(self):
        from syslens.collectors.stack_dump import _find_cdb
        with patch("os.path.isfile", return_value=False):
            assert _find_cdb() is None

    def test_returns_first_found_path(self):
        from syslens.collectors.stack_dump import _find_cdb, _CDB_SEARCH_DIRS
        expected = os.path.join(_CDB_SEARCH_DIRS[0], "cdb.exe")
        with patch("os.path.isfile", side_effect=lambda p: p == expected):
            result = _find_cdb()
        assert result == expected


# ===========================================================================
# _is_python_exe()
# ===========================================================================

class TestIsPythonExe:
    @pytest.mark.parametrize("exe,expected", [
        (r"C:\Python312\python.exe", True),
        (r"C:\Python312\pythonw.exe", True),
        (r"/usr/bin/python3", True),
        (r"C:\Windows\notepad.exe", False),
        (r"/usr/bin/bash", False),
        (None, False),
        ("", False),
    ])
    def test_detection(self, exe, expected):
        from syslens.collectors.stack_dump import _is_python_exe
        assert _is_python_exe(exe) == expected


# ===========================================================================
# _psutil_fallback()
# ===========================================================================

class TestPsutilFallback:
    def test_returns_thread_list_from_proc(self):
        from syslens.collectors.stack_dump import _psutil_fallback
        import psutil

        t1 = MagicMock(); t1.id = 100; t1.user_time = 1.5; t1.system_time = 0.3
        t2 = MagicMock(); t2.id = 101; t2.user_time = 0.0; t2.system_time = 0.1
        proc = MagicMock()
        proc.threads.return_value = [t1, t2]

        result = _psutil_fallback(proc)
        assert result["method"] == "psutil-threads"
        assert len(result["threads"]) == 2
        assert "100" in result["threads"][0]["header"]
        assert "101" in result["threads"][1]["header"]

    def test_thread_header_includes_timing(self):
        from syslens.collectors.stack_dump import _psutil_fallback
        t = MagicMock(); t.id = 55; t.user_time = 2.123; t.system_time = 0.456
        proc = MagicMock(); proc.threads.return_value = [t]
        result = _psutil_fallback(proc)
        header = result["threads"][0]["header"]
        assert "2.123" in header
        assert "0.456" in header

    def test_thread_frame_contains_no_debugger_message(self):
        from syslens.collectors.stack_dump import _psutil_fallback
        t = MagicMock(); t.id = 1; t.user_time = 0.0; t.system_time = 0.0
        proc = MagicMock(); proc.threads.return_value = [t]
        result = _psutil_fallback(proc)
        assert result["threads"][0]["frames"] == [
            "[No debugger available — stack frames not captured]"
        ]

    def test_returns_none_method_on_access_denied(self):
        import psutil
        from syslens.collectors.stack_dump import _psutil_fallback
        proc = MagicMock()
        proc.threads.side_effect = psutil.AccessDenied(0)
        result = _psutil_fallback(proc)
        assert result["method"] == "none"
        assert result["threads"] == []

    def test_returns_none_method_on_no_such_process(self):
        import psutil
        from syslens.collectors.stack_dump import _psutil_fallback
        proc = MagicMock()
        proc.threads.side_effect = psutil.NoSuchProcess(0)
        result = _psutil_fallback(proc)
        assert result["method"] == "none"


# ===========================================================================
# _get_traces() — platform dispatch
# ===========================================================================

class TestGetTraces:
    """Test that _get_traces dispatches to the right tool on each platform."""

    def _patch_sys(self, system_name):
        import syslens.collectors.stack_dump as sd
        return patch.object(sys.modules["syslens.collectors.stack_dump"],
                            "_SYS", system_name)

    def test_tries_pyspy_first_for_python_exe(self):
        from syslens.collectors.stack_dump import _get_traces
        pyspy_result = {"method": "py-spy", "raw": "", "threads": []}
        with patch("syslens.collectors.stack_dump._is_python_exe", return_value=True):
            with patch("syslens.collectors.stack_dump._try_pyspy",
                       return_value=pyspy_result) as mock_pyspy:
                result = _get_traces(123, r"C:\Python312\python.exe")
        mock_pyspy.assert_called_once_with(123)
        assert result is pyspy_result

    def test_windows_falls_through_to_dbghelp_when_cdb_absent(self):
        from syslens.collectors.stack_dump import _get_traces
        dbghelp_result = {"method": "dbghelp", "raw": "", "threads": []}
        with self._patch_sys("Windows"):
            with patch("syslens.collectors.stack_dump._is_python_exe", return_value=False):
                with patch("syslens.collectors.stack_dump._try_cdb", return_value=None):
                    with patch("syslens.collectors.stack_dump._try_dbghelp_windows",
                               return_value=dbghelp_result) as mock_dbg:
                        result = _get_traces(123, "notepad.exe")
        mock_dbg.assert_called_once_with(123)
        assert result is dbghelp_result

    def test_windows_returns_cdb_when_available(self):
        from syslens.collectors.stack_dump import _get_traces
        cdb_result = {"method": "cdb", "raw": "", "threads": []}
        with self._patch_sys("Windows"):
            with patch("syslens.collectors.stack_dump._is_python_exe", return_value=False):
                with patch("syslens.collectors.stack_dump._try_cdb",
                           return_value=cdb_result) as mock_cdb:
                    result = _get_traces(123, "notepad.exe")
        mock_cdb.assert_called_once_with(123)
        assert result is cdb_result

    def test_windows_falls_back_to_pyspy_when_all_native_fail(self):
        from syslens.collectors.stack_dump import _get_traces
        pyspy_result = {"method": "py-spy", "raw": "", "threads": []}
        with self._patch_sys("Windows"):
            with patch("syslens.collectors.stack_dump._is_python_exe", return_value=False):
                with patch("syslens.collectors.stack_dump._try_cdb", return_value=None):
                    with patch("syslens.collectors.stack_dump._try_dbghelp_windows",
                               return_value=None):
                        with patch("syslens.collectors.stack_dump._try_pyspy",
                                   return_value=pyspy_result):
                            result = _get_traces(123, "notepad.exe")
        assert result is pyspy_result

    def test_windows_returns_none_when_everything_fails(self):
        from syslens.collectors.stack_dump import _get_traces
        with self._patch_sys("Windows"):
            with patch("syslens.collectors.stack_dump._is_python_exe", return_value=False):
                with patch("syslens.collectors.stack_dump._try_cdb", return_value=None):
                    with patch("syslens.collectors.stack_dump._try_dbghelp_windows",
                               return_value=None):
                        with patch("syslens.collectors.stack_dump._try_pyspy",
                                   return_value=None):
                            result = _get_traces(123, "notepad.exe")
        assert result is None

    def test_darwin_uses_lldb(self):
        from syslens.collectors.stack_dump import _get_traces
        lldb_result = {"method": "lldb", "raw": "", "threads": []}
        with self._patch_sys("Darwin"):
            with patch("syslens.collectors.stack_dump._is_python_exe", return_value=False):
                with patch("syslens.collectors.stack_dump._try_lldb",
                           return_value=lldb_result) as mock_lldb:
                    result = _get_traces(123, "/usr/bin/someapp")
        mock_lldb.assert_called_once_with(123)
        assert result is lldb_result

    def test_linux_uses_gdb(self):
        from syslens.collectors.stack_dump import _get_traces
        gdb_result = {"method": "gdb", "raw": "", "threads": []}
        with self._patch_sys("Linux"):
            with patch("syslens.collectors.stack_dump._is_python_exe", return_value=False):
                with patch("syslens.collectors.stack_dump._try_gdb",
                           return_value=gdb_result) as mock_gdb:
                    result = _get_traces(123, "/usr/bin/myapp")
        mock_gdb.assert_called_once_with(123)
        assert result is gdb_result


# ===========================================================================
# collect_dump() — top-level entry point
# ===========================================================================

class TestCollectDump:

    def _make_full_trace(self, method="py-spy"):
        return {
            "method": method,
            "raw": "some raw output",
            "threads": [{"header": "Thread 1", "frames": ["frame_a"]}],
        }

    def test_returns_error_when_process_not_found(self):
        from syslens.collectors.stack_dump import collect_dump
        with patch("syslens.collectors.stack_dump._find_process", return_value=None):
            result = collect_dump("nonexistent_xyz")
        assert "error" in result
        assert "nonexistent_xyz" in result["error"]

    def test_returns_process_metadata_on_success(self):
        from syslens.collectors.stack_dump import collect_dump
        proc = _make_proc(pid=42, name="test.exe")
        trace = self._make_full_trace()
        with patch("syslens.collectors.stack_dump._find_process", return_value=proc):
            with patch("syslens.collectors.stack_dump._get_traces", return_value=trace):
                result = collect_dump("test.exe")

        assert result["pid"] == 42
        assert result["name"] == "test.exe"
        assert result["status"] == "running"
        assert result["method"] == "py-spy"
        assert result["threads"] == trace["threads"]

    def test_falls_back_to_psutil_when_get_traces_returns_none(self):
        from syslens.collectors.stack_dump import collect_dump
        proc = _make_proc()
        psutil_trace = {
            "method": "psutil-threads",
            "raw": "",
            "threads": [{"header": "Thread 1234", "frames": []}],
        }
        with patch("syslens.collectors.stack_dump._find_process", return_value=proc):
            with patch("syslens.collectors.stack_dump._get_traces", return_value=None):
                with patch("syslens.collectors.stack_dump._psutil_fallback",
                           return_value=psutil_trace) as mock_fb:
                    result = collect_dump("notepad.exe")
        mock_fb.assert_called_once_with(proc)
        assert result["method"] == "psutil-threads"

    def test_handles_access_denied_on_proc_info(self):
        import psutil
        from syslens.collectors.stack_dump import collect_dump
        proc = MagicMock()
        proc.pid = 1
        proc.name.side_effect = psutil.AccessDenied(1)
        with patch("syslens.collectors.stack_dump._find_process", return_value=proc):
            result = collect_dump("1")
        # Should either return an error dict or a partial result — must not raise
        assert isinstance(result, dict)

    def test_accepts_integer_pid_string(self):
        from syslens.collectors.stack_dump import collect_dump
        proc = _make_proc(pid=100)
        trace = self._make_full_trace()
        with patch("syslens.collectors.stack_dump._find_process", return_value=proc) as mock_fp:
            with patch("syslens.collectors.stack_dump._get_traces", return_value=trace):
                collect_dump("100")
        mock_fp.assert_called_once_with("100")

    def test_result_contains_all_expected_keys(self):
        from syslens.collectors.stack_dump import collect_dump
        proc = _make_proc()
        trace = self._make_full_trace()
        with patch("syslens.collectors.stack_dump._find_process", return_value=proc):
            with patch("syslens.collectors.stack_dump._get_traces", return_value=trace):
                result = collect_dump("notepad.exe")

        for key in ("pid", "name", "status", "exe", "cmdline",
                    "username", "num_threads", "method", "threads"):
            assert key in result, f"Missing key: {key}"

    def test_num_threads_defaults_to_zero_when_access_denied(self):
        import psutil
        from syslens.collectors.stack_dump import collect_dump
        proc = _make_proc()
        proc.num_threads.side_effect = psutil.AccessDenied(0)
        trace = self._make_full_trace()
        with patch("syslens.collectors.stack_dump._find_process", return_value=proc):
            with patch("syslens.collectors.stack_dump._get_traces", return_value=trace):
                result = collect_dump("notepad.exe")
        assert result["num_threads"] == 0


# ===========================================================================
# display.render_dump()
# ===========================================================================

class TestRenderDump:
    """Tests for the Rich renderer — uses record=True to capture output."""

    def _render(self, data):
        """Render to a captured string."""
        from syslens import display
        c = Console(record=True, width=120)
        original = display.console
        display.console = c
        try:
            display.render_dump(data)
        finally:
            display.console = original
        return c.export_text()

    def test_renders_error_dict_without_raising(self):
        out = self._render({"error": "No process found matching: ghost"})
        assert "ghost" in out

    def test_renders_process_metadata_without_raising(self):
        data = {
            "pid": 42,
            "name": "notepad.exe",
            "status": "running",
            "exe": r"C:\Windows\notepad.exe",
            "cmdline": "notepad.exe",
            "username": "DESKTOP\\user",
            "num_threads": 2,
            "method": "py-spy",
            "raw": "",
            "threads": [
                {"header": "Thread 0x1 (active)", "frames": ["my_func at app.py:10"]},
            ],
        }
        out = self._render(data)
        assert "notepad.exe" in out
        assert "42" in out

    def test_renders_psutil_fallback_method(self):
        data = {
            "pid": 99,
            "name": "myapp",
            "status": "running",
            "exe": None,
            "cmdline": None,
            "username": None,
            "num_threads": 1,
            "method": "psutil-threads",
            "raw": "",
            "threads": [
                {"header": "Thread 1000  (user=0.100s  sys=0.010s)", "frames": [
                    "[No debugger available — stack frames not captured]"
                ]},
            ],
        }
        out = self._render(data)
        assert "Thread 1000" in out

    def test_renders_empty_threads_gracefully(self):
        data = {
            "pid": 5,
            "name": "test",
            "status": "sleeping",
            "exe": "/usr/bin/test",
            "cmdline": "test",
            "username": "root",
            "num_threads": 0,
            "method": "none",
            "raw": "",
            "threads": [],
        }
        # Should not raise
        self._render(data)

    def test_renders_unknown_method_without_raising(self):
        data = {
            "pid": 7,
            "name": "oddapp",
            "status": "running",
            "exe": None,
            "cmdline": None,
            "username": None,
            "num_threads": 1,
            "method": "future-unknown-tool",
            "raw": "",
            "threads": [{"header": "Thread 1", "frames": ["frame1"]}],
        }
        self._render(data)  # must not raise

    @pytest.mark.parametrize("method_key,expected_label", [
        ("py-spy",         "py-spy"),
        ("cdb",            "Windows Debugger (cdb)"),
        ("dbghelp",        "DbgHelp.dll (native)"),
        ("gdb",            "GDB"),
        ("lldb",           "LLDB"),
        ("psutil-threads", "psutil (thread IDs only)"),
        ("none",           "none"),
    ])
    def test_method_label_present_in_output(self, method_key, expected_label):
        data = {
            "pid": 1, "name": "p", "status": "running",
            "exe": None, "cmdline": None, "username": None,
            "num_threads": 0, "method": method_key, "raw": "",
            "threads": [],
        }
        out = self._render(data)
        assert expected_label in out

    def test_rich_markup_in_frame_is_escaped(self):
        """Frames containing '[' must not crash the Rich renderer."""
        data = {
            "pid": 1, "name": "p", "status": "running",
            "exe": None, "cmdline": None, "username": None,
            "num_threads": 1, "method": "gdb", "raw": "",
            "threads": [
                {"header": "Thread 1", "frames": ["[0xdeadbeef] some_func+0x10"]}
            ],
        }
        # Should not raise MarkupError
        self._render(data)


# ===========================================================================
# main.py --dump flag integration (Typer test client)
# ===========================================================================

class TestMainDumpFlag:
    """Test CLI routing for --dump through Typer's test runner."""

    def test_dump_flag_calls_collect_dump(self):
        from typer.testing import CliRunner
        from syslens.main import app
        runner = CliRunner()

        dump_result = {
            "pid": 1, "name": "test", "status": "running",
            "exe": None, "cmdline": None, "username": None,
            "num_threads": 0, "method": "none", "raw": "", "threads": [],
        }
        with patch("syslens.collectors.stack_dump.collect_dump",
                   return_value=dump_result) as mock_cd:
            with patch("syslens.display.render_dump"):
                result = runner.invoke(app, ["--dump", "notepad.exe"])

        mock_cd.assert_called_once_with("notepad.exe")
        assert result.exit_code == 0

    def test_dump_json_flag_produces_valid_json(self):
        from typer.testing import CliRunner
        import json
        from syslens.main import app
        runner = CliRunner()

        dump_result = {
            "pid": 1, "name": "test", "status": "running",
            "exe": None, "cmdline": None, "username": None,
            "num_threads": 0, "method": "none", "raw": "", "threads": [],
        }
        with patch("syslens.collectors.stack_dump.collect_dump",
                   return_value=dump_result):
            result = runner.invoke(app, ["--dump", "notepad.exe", "--json"])

        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["pid"] == 1
        assert parsed["method"] == "none"

    def test_dump_error_result_renders_without_crash(self):
        from typer.testing import CliRunner
        from syslens.main import app
        runner = CliRunner()

        with patch("syslens.collectors.stack_dump.collect_dump",
                   return_value={"error": "No process found matching: ghost"}):
            result = runner.invoke(app, ["--dump", "ghost"])

        assert result.exit_code == 0

    def test_dump_does_not_invoke_other_collectors(self):
        from typer.testing import CliRunner
        from syslens.main import app
        runner = CliRunner()

        dump_result = {
            "pid": 1, "name": "t", "status": "running",
            "exe": None, "cmdline": None, "username": None,
            "num_threads": 0, "method": "none", "raw": "", "threads": [],
        }
        with patch("syslens.collectors.stack_dump.collect_dump",
                   return_value=dump_result):
            with patch("syslens.display.render_dump"):
                with patch("syslens.collectors.cpu.collect") as mock_cpu:
                    result = runner.invoke(app, ["--dump", "1234"])

        mock_cpu.assert_not_called()
        assert result.exit_code == 0
