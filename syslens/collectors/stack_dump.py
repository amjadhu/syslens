"""Stack dump collector — captures thread stack traces for a target process."""

import os
import platform
import struct
import subprocess

import psutil

_SYS = platform.system()


def _safe(fn):
    try:
        return fn()
    except (psutil.AccessDenied, psutil.NoSuchProcess, OSError):
        return None


def _find_process(target):
    """Find process by PID (numeric) or name (string, case-insensitive, first match)."""
    target_str = str(target).strip()
    if target_str.isdigit():
        try:
            return psutil.Process(int(target_str))
        except psutil.NoSuchProcess:
            return None
    # Exact name match first
    matches = [
        p for p in psutil.process_iter(["name"])
        if (p.info["name"] or "").lower() == target_str.lower()
    ]
    if not matches:
        # Partial match fallback
        matches = [
            p for p in psutil.process_iter(["name"])
            if target_str.lower() in (p.info["name"] or "").lower()
        ]
    return matches[0] if matches else None


def _run(cmd, timeout=20):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                           errors="ignore")
        return (r.stdout or "").strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError, PermissionError):
        return ""


# ── py-spy (Python processes) ─────────────────────────────────────────────────

def _try_pyspy(pid):
    out = _run(["py-spy", "dump", "--pid", str(pid)], timeout=20)
    if out and ("Thread" in out or "thread" in out):
        return {"method": "py-spy", "raw": out, "threads": _parse_pyspy(out)}
    return None


def _parse_pyspy(output):
    threads = []
    current = None
    for line in output.splitlines():
        if line.startswith("Thread ") or (line and not line.startswith(" ") and "thread" in line.lower()):
            if current is not None:
                threads.append(current)
            current = {"header": line.rstrip(), "frames": []}
        elif current is not None and line.startswith("    "):
            current["frames"].append(line.strip())
    if current is not None:
        threads.append(current)
    return threads


# ── cdb (Windows Debugging Tools) ────────────────────────────────────────────

_CDB_SEARCH_DIRS = [
    r"C:\Program Files (x86)\Windows Kits\10\Debuggers\x64",
    r"C:\Program Files (x86)\Windows Kits\10\Debuggers\x86",
    r"C:\Program Files\Windows Kits\10\Debuggers\x64",
    r"C:\Program Files\Windows Kits\10\Debuggers\x86",
    r"C:\Program Files\Windows Kits\11\Debuggers\x64",
]

def _find_cdb():
    # Traditional Windows Debugging Tools (Windows SDK) layout only.
    # WinDbg Preview (winget/Store) puts stubs in WindowsApps that launch the
    # GUI and return no output — those are not usable for command-line attach.
    for d in _CDB_SEARCH_DIRS:
        cdb = os.path.join(d, "cdb.exe")
        if os.path.isfile(cdb):
            return cdb
    return None


def _try_cdb(pid):
    cdb = _find_cdb()
    if not cdb:
        return None
    # Attach, dump all thread stacks with frame numbers, then quit
    out = _run([cdb, "-p", str(pid), "-c", "~*kn; q"], timeout=25)
    if out and ("RetAddr" in out or "Child-SP" in out or "ChildEBP" in out):
        return {"method": "cdb", "raw": out, "threads": _parse_cdb(out)}
    return None


def _parse_cdb(output):
    """Parse cdb ~*kn output into threads with frames."""
    threads = []
    current = None
    for line in output.splitlines():
        s = line.strip()
        # Thread header: "   0  Id: 1a2c.1a30 Suspend: 1 ..."
        if s and s[0].isdigit() and "Id:" in s:
            if current is not None:
                threads.append(current)
            current = {"header": s, "frames": []}
        elif current is not None and s and (s[0].isdigit() or s.startswith("RetAddr") or s.startswith("Child")):
            current["frames"].append(s)
    if current is not None:
        threads.append(current)
    return threads


# ── gdb (Linux) ───────────────────────────────────────────────────────────────

def _try_gdb(pid):
    cmd = ["gdb", "--batch",
           "-ex", "set pagination off",
           "-ex", "thread apply all bt",
           "-ex", "quit",
           "-p", str(pid)]
    out = _run(cmd, timeout=20)
    if out and "Thread " in out:
        return {"method": "gdb", "raw": out, "threads": _parse_gdb(out)}
    return None


def _parse_gdb(output):
    threads = []
    current = None
    for line in output.splitlines():
        s = line.strip()
        if s.startswith("Thread ") and "(" in s:
            if current is not None:
                threads.append(current)
            current = {"header": s, "frames": []}
        elif current is not None and s.startswith("#"):
            current["frames"].append(s)
    if current is not None:
        threads.append(current)
    return threads


# ── lldb (macOS) ─────────────────────────────────────────────────────────────

def _try_lldb(pid):
    cmd = ["lldb", "-p", str(pid), "--batch",
           "-o", "thread backtrace all",
           "-o", "quit"]
    out = _run(cmd, timeout=20)
    if out and "frame #" in out:
        return {"method": "lldb", "raw": out, "threads": _parse_lldb(out)}
    return None


def _parse_lldb(output):
    threads = []
    current = None
    for line in output.splitlines():
        s = line.strip()
        if s.startswith("* thread") or (s.startswith("thread #") and ":" in s):
            if current is not None:
                threads.append(current)
            current = {"header": s, "frames": []}
        elif current is not None and "frame #" in s:
            current["frames"].append(s)
    if current is not None:
        threads.append(current)
    return threads


# ── DbgHelp.dll native walker (Windows, no external tools) ───────────────────

def _try_dbghelp_windows(pid):
    """Walk stacks via DbgHelp.dll + ctypes — always available on Windows."""
    try:
        import ctypes
        import ctypes.wintypes as wt
        import struct
    except ImportError:
        return None

    try:
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        dbg = ctypes.WinDLL("dbghelp",  use_last_error=True)
    except OSError:
        return None

    PROCESS_QUERY_INFORMATION = 0x0400
    PROCESS_VM_READ           = 0x0010
    THREAD_GET_CONTEXT        = 0x0008
    THREAD_SUSPEND_RESUME     = 0x0002
    TH32CS_SNAPTHREAD         = 0x00000004
    IMAGE_FILE_MACHINE_AMD64  = 0x8664
    CONTEXT_FULL              = 0x10007F
    CONTEXT_SIZE              = 1232        # sizeof(CONTEXT) x64
    SYMOPT_UNDNAME            = 0x00000002
    SYMOPT_DEFERRED_LOADS     = 0x00000004
    MAX_SYM_NAME              = 256
    # x64 CONTEXT field offsets (from winnt.h)
    OFF_CONTEXT_FLAGS = 0x30
    OFF_RSP           = 0x98
    OFF_RBP           = 0xA0
    OFF_RIP           = 0xF8

    class THREADENTRY32(ctypes.Structure):
        _fields_ = [
            ("dwSize",             wt.DWORD),
            ("cntUsage",           wt.DWORD),
            ("th32ThreadID",       wt.DWORD),
            ("th32OwnerProcessID", wt.DWORD),
            ("tpBasePri",          ctypes.c_long),
            ("tpDeltaPri",         ctypes.c_long),
            ("dwFlags",            wt.DWORD),
        ]

    class ADDRESS64(ctypes.Structure):
        _fields_ = [
            ("Offset",  ctypes.c_uint64),
            ("Segment", ctypes.c_uint16),
            ("Mode",    ctypes.c_uint32),
        ]

    class KDHELP64(ctypes.Structure):
        _fields_ = [
            ("Thread",                       ctypes.c_uint64),
            ("ThCallbackStack",              ctypes.c_uint32),
            ("ThCallbackBStore",             ctypes.c_uint32),
            ("NextCallback",                 ctypes.c_uint32),
            ("FramePointer",                 ctypes.c_uint32),
            ("KiCallUserMode",               ctypes.c_uint64),
            ("KeUserCallbackDispatcher",     ctypes.c_uint64),
            ("SystemRangeStart",             ctypes.c_uint64),
            ("KiUserExceptionDispatcher",    ctypes.c_uint64),
            ("StackBase",                    ctypes.c_uint64),
            ("StackLimit",                   ctypes.c_uint64),
            ("BuildVersion",                 ctypes.c_uint32),
            ("RetpolineStubFunctionTableSize", ctypes.c_uint32),
            ("RetpolineStubFunctionTable",   ctypes.c_uint64),
            ("RetpolineStubOffset",          ctypes.c_uint32),
            ("RetpolineStubSize",            ctypes.c_uint32),
            ("Reserved0",                    ctypes.c_uint64 * 2),
        ]

    class STACKFRAME64(ctypes.Structure):
        _fields_ = [
            ("AddrPC",         ADDRESS64),
            ("AddrReturn",     ADDRESS64),
            ("AddrFrame",      ADDRESS64),
            ("AddrStack",      ADDRESS64),
            ("AddrBStore",     ADDRESS64),
            ("FuncTableEntry", ctypes.c_void_p),
            ("Params",         ctypes.c_uint64 * 4),
            ("Far",            wt.BOOL),
            ("Virtual",        wt.BOOL),
            ("Reserved",       ctypes.c_uint64 * 3),
            ("KdHelp",         KDHELP64),
        ]

    class SYMBOL_INFO(ctypes.Structure):
        _fields_ = [
            ("SizeOfStruct", ctypes.c_uint32),
            ("TypeIndex",    ctypes.c_uint32),
            ("Reserved",     ctypes.c_uint64 * 2),
            ("Index",        ctypes.c_uint32),
            ("Size",         ctypes.c_uint32),
            ("ModBase",      ctypes.c_uint64),
            ("Flags",        ctypes.c_uint32),
            ("Value",        ctypes.c_uint64),
            ("Address",      ctypes.c_uint64),
            ("Register",     ctypes.c_uint32),
            ("Scope",        ctypes.c_uint32),
            ("Tag",          ctypes.c_uint32),
            ("NameLen",      ctypes.c_uint32),
            ("MaxNameLen",   ctypes.c_uint32),
            ("Name",         ctypes.c_char * MAX_SYM_NAME),
        ]

    class IMAGEHLP_MODULE64(ctypes.Structure):
        _fields_ = [
            ("SizeOfStruct",   ctypes.c_uint32),
            ("BaseOfImage",    ctypes.c_uint64),
            ("ImageSize",      ctypes.c_uint32),
            ("TimeDateStamp",  ctypes.c_uint32),
            ("CheckSum",       ctypes.c_uint32),
            ("NumSyms",        ctypes.c_uint32),
            ("SymType",        ctypes.c_uint32),
            ("ModuleName",     ctypes.c_char * 32),
            ("ImageName",      ctypes.c_char * 256),
            ("LoadedImageName", ctypes.c_char * 256),
            ("LoadedPdbName",  ctypes.c_char * 256),
            ("CVSig",          ctypes.c_uint32),
            ("CVData",         ctypes.c_char * 780),
            ("PdbSig",         ctypes.c_uint32),
            ("PdbSig70",       ctypes.c_byte * 16),
            ("PdbAge",         ctypes.c_uint32),
            ("PdbUnmatched",   ctypes.c_uint32),
            ("DbgUnmatched",   ctypes.c_uint32),
            ("LineNumbers",    ctypes.c_uint32),
            ("GlobalSymbols",  ctypes.c_uint32),
            ("TypeInfo",       ctypes.c_uint32),
            ("SourceIndexed",  ctypes.c_uint32),
            ("Publics",        ctypes.c_uint32),
            ("MachineType",    ctypes.c_uint32),
            ("Reserved",       ctypes.c_uint32),
        ]

    # Set up dbghelp function signatures
    dbg.SymSetOptions.argtypes = [wt.DWORD]
    dbg.SymSetOptions.restype  = wt.DWORD
    dbg.SymInitialize.argtypes = [ctypes.c_void_p, ctypes.c_char_p, wt.BOOL]
    dbg.SymInitialize.restype  = wt.BOOL
    dbg.SymCleanup.argtypes    = [ctypes.c_void_p]
    dbg.SymCleanup.restype     = wt.BOOL
    dbg.SymFromAddr.argtypes   = [ctypes.c_void_p, ctypes.c_uint64,
                                   ctypes.POINTER(ctypes.c_uint64),
                                   ctypes.c_void_p]
    dbg.SymFromAddr.restype    = wt.BOOL
    dbg.SymGetModuleBase64.argtypes = [ctypes.c_void_p, ctypes.c_uint64]
    dbg.SymGetModuleBase64.restype  = ctypes.c_uint64
    dbg.SymGetModuleInfo64.argtypes = [ctypes.c_void_p, ctypes.c_uint64,
                                        ctypes.POINTER(IMAGEHLP_MODULE64)]
    dbg.SymGetModuleInfo64.restype  = wt.BOOL
    dbg.SymFunctionTableAccess64.argtypes = [ctypes.c_void_p, ctypes.c_uint64]
    dbg.SymFunctionTableAccess64.restype  = ctypes.c_void_p
    dbg.StackWalk64.argtypes = [
        wt.DWORD, ctypes.c_void_p, ctypes.c_void_p,
        ctypes.c_void_p, ctypes.c_void_p,
        ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
    ]
    dbg.StackWalk64.restype = wt.BOOL
    k32.OpenProcess.argtypes    = [wt.DWORD, wt.BOOL, wt.DWORD]
    k32.OpenProcess.restype     = ctypes.c_void_p
    k32.OpenThread.argtypes     = [wt.DWORD, wt.BOOL, wt.DWORD]
    k32.OpenThread.restype      = ctypes.c_void_p
    k32.CloseHandle.argtypes    = [ctypes.c_void_p]
    k32.CloseHandle.restype     = wt.BOOL
    k32.SuspendThread.argtypes  = [ctypes.c_void_p]
    k32.SuspendThread.restype   = wt.DWORD
    k32.ResumeThread.argtypes   = [ctypes.c_void_p]
    k32.ResumeThread.restype    = wt.DWORD
    k32.GetThreadContext.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    k32.GetThreadContext.restype  = wt.BOOL
    k32.CreateToolhelp32Snapshot.argtypes = [wt.DWORD, wt.DWORD]
    k32.CreateToolhelp32Snapshot.restype  = ctypes.c_void_p
    k32.Thread32First.argtypes = [ctypes.c_void_p, ctypes.POINTER(THREADENTRY32)]
    k32.Thread32First.restype  = wt.BOOL
    k32.Thread32Next.argtypes  = [ctypes.c_void_p, ctypes.POINTER(THREADENTRY32)]
    k32.Thread32Next.restype   = wt.BOOL
    k32.ReadProcessMemory.argtypes = [ctypes.c_void_p, ctypes.c_void_p,
                                      ctypes.c_void_p, ctypes.c_size_t,
                                      ctypes.POINTER(ctypes.c_size_t)]
    k32.ReadProcessMemory.restype  = wt.BOOL

    try:
        hProcess = k32.OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, pid)
        if not hProcess:
            return None

        try:
            dbg.SymSetOptions(SYMOPT_UNDNAME | SYMOPT_DEFERRED_LOADS)
            if not dbg.SymInitialize(hProcess, None, True):
                return None

            # ── PE export-table helpers (for symbol resolution without PDB) ───

            export_cache = {}  # mod_base -> sorted [(rva, name)]

            def _rpmem(addr, size):
                buf = ctypes.create_string_buffer(size)
                n = ctypes.c_size_t(0)
                k32.ReadProcessMemory(hProcess, ctypes.c_void_p(addr),
                                      buf, size, ctypes.byref(n))
                return bytes(buf[:n.value])

            def _get_exports(mod_base):
                if mod_base in export_cache:
                    return export_cache[mod_base]
                try:
                    dos = _rpmem(mod_base, 64)
                    if len(dos) < 64 or dos[:2] != b'MZ':
                        export_cache[mod_base] = []; return []
                    e_lfanew = struct.unpack_from('<I', dos, 60)[0]
                    pe = _rpmem(mod_base + e_lfanew, 264)
                    if len(pe) < 264 or pe[:4] != b'PE\x00\x00':
                        export_cache[mod_base] = []; return []
                    magic = struct.unpack_from('<H', pe, 24)[0]
                    exp_rva = struct.unpack_from('<I', pe, 24 + (112 if magic == 0x20B else 96))[0]
                    if exp_rva == 0:
                        export_cache[mod_base] = []; return []
                    ed = _rpmem(mod_base + exp_rva, 40)
                    if len(ed) < 40:
                        export_cache[mod_base] = []; return []
                    # IMAGE_EXPORT_DIRECTORY field offsets (winnt.h):
                    #  0: Characteristics, 4: TimeDateStamp, 8: MajorVersion,
                    # 10: MinorVersion, 12: Name (RVA), 16: Base,
                    # 20: NumberOfFunctions, 24: NumberOfNames,
                    # 28: AddressOfFunctions, 32: AddressOfNames,
                    # 36: AddressOfNameOrdinals
                    num_funcs         = struct.unpack_from('<I', ed, 20)[0]
                    num_names         = struct.unpack_from('<I', ed, 24)[0]
                    addr_funcs_rva    = struct.unpack_from('<I', ed, 28)[0]
                    addr_names_rva    = struct.unpack_from('<I', ed, 32)[0]
                    addr_ordinals_rva = struct.unpack_from('<I', ed, 36)[0]
                    if num_names == 0:
                        export_cache[mod_base] = []; return []
                    funcs    = _rpmem(mod_base + addr_funcs_rva,    4 * num_funcs)
                    names    = _rpmem(mod_base + addr_names_rva,    4 * num_names)
                    ordinals = _rpmem(mod_base + addr_ordinals_rva, 2 * num_names)
                    if len(names) < 4 * num_names or len(ordinals) < 2 * num_names:
                        export_cache[mod_base] = []; return []
                    exports = []
                    for i in range(num_names):
                        name_rva = struct.unpack_from('<I', names,    i * 4)[0]
                        ordinal  = struct.unpack_from('<H', ordinals, i * 2)[0]
                        if ordinal * 4 + 4 > len(funcs):
                            continue
                        func_rva = struct.unpack_from('<I', funcs, ordinal * 4)[0]
                        raw = _rpmem(mod_base + name_rva, 128)
                        nul = raw.find(b'\x00')
                        fname = raw[:nul].decode('ascii', errors='ignore') if nul >= 0 else ''
                        if fname:
                            exports.append((func_rva, fname))
                    exports.sort(key=lambda x: x[0])
                    export_cache[mod_base] = exports
                    return exports
                except Exception:
                    export_cache[mod_base] = []
                    return []

            def _resolve_export(mod_base, pc):
                """Binary-search exports for the closest function at or before pc."""
                exports = _get_exports(mod_base)
                if not exports:
                    return None
                rva = pc - mod_base
                lo, hi, best = 0, len(exports) - 1, None
                while lo <= hi:
                    mid = (lo + hi) // 2
                    if exports[mid][0] <= rva:
                        best = exports[mid]
                        lo = mid + 1
                    else:
                        hi = mid - 1
                if best is None:
                    return None
                return best[1], rva - best[0]  # (func_name, offset)

            # ── Enumerate threads belonging to pid ─────────────────────────
            hSnap = k32.CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD, 0)
            te = THREADENTRY32()
            te.dwSize = ctypes.sizeof(THREADENTRY32)
            thread_ids = []
            if k32.Thread32First(hSnap, ctypes.byref(te)):
                while True:
                    if te.th32OwnerProcessID == pid:
                        thread_ids.append(te.th32ThreadID)
                    te.dwSize = ctypes.sizeof(THREADENTRY32)
                    if not k32.Thread32Next(hSnap, ctypes.byref(te)):
                        break
            k32.CloseHandle(hSnap)

            threads_out = []
            for tid in thread_ids:
                hThread = k32.OpenThread(
                    THREAD_GET_CONTEXT | THREAD_SUSPEND_RESUME, False, tid)
                if not hThread:
                    threads_out.append(
                        {"header": f"Thread {tid}", "frames": ["[access denied]"]})
                    continue
                try:
                    k32.SuspendThread(hThread)

                    # Allocate 16-byte-aligned CONTEXT buffer
                    raw = (ctypes.c_byte * (CONTEXT_SIZE + 15))()
                    base = ctypes.addressof(raw)
                    aligned = (base + 15) & ~15
                    ctypes.memset(ctypes.c_void_p(aligned), 0, CONTEXT_SIZE)
                    # Write ContextFlags at offset 0x30
                    ctypes.memmove(aligned + OFF_CONTEXT_FLAGS,
                                   ctypes.byref(ctypes.c_uint32(CONTEXT_FULL)), 4)

                    frames = []
                    if k32.GetThreadContext(hThread, ctypes.c_void_p(aligned)):
                        buf = bytes((ctypes.c_byte * CONTEXT_SIZE).from_address(aligned))
                        rip = struct.unpack_from("<Q", buf, OFF_RIP)[0]
                        rsp = struct.unpack_from("<Q", buf, OFF_RSP)[0]
                        rbp = struct.unpack_from("<Q", buf, OFF_RBP)[0]

                        sf = STACKFRAME64()
                        sf.AddrPC.Offset    = rip;  sf.AddrPC.Mode    = 3
                        sf.AddrStack.Offset = rsp;  sf.AddrStack.Mode = 3
                        sf.AddrFrame.Offset = rbp;  sf.AddrFrame.Mode = 3

                        for _ in range(64):
                            ok = dbg.StackWalk64(
                                IMAGE_FILE_MACHINE_AMD64,
                                hProcess, hThread,
                                ctypes.byref(sf),
                                ctypes.c_void_p(aligned),
                                None,
                                dbg.SymFunctionTableAccess64,
                                dbg.SymGetModuleBase64,
                                None,
                            )
                            if not ok or sf.AddrPC.Offset == 0:
                                break

                            pc = sf.AddrPC.Offset
                            sym_buf = ctypes.create_string_buffer(
                                ctypes.sizeof(SYMBOL_INFO) + MAX_SYM_NAME)
                            sym = SYMBOL_INFO.from_buffer(sym_buf)
                            sym.SizeOfStruct = ctypes.sizeof(SYMBOL_INFO)
                            sym.MaxNameLen   = MAX_SYM_NAME

                            disp = ctypes.c_uint64(0)
                            if dbg.SymFromAddr(hProcess, pc,
                                               ctypes.byref(disp),
                                               ctypes.byref(sym)):
                                name = sym.Name.decode("utf-8", errors="ignore")
                                frames.append(f"{name}+0x{disp.value:x}  [{pc:#x}]")
                            else:
                                # SymFromAddr failed — try PE export table, then module+offset
                                mod_info = IMAGEHLP_MODULE64()
                                mod_info.SizeOfStruct = ctypes.sizeof(IMAGEHLP_MODULE64)
                                if dbg.SymGetModuleInfo64(hProcess, pc,
                                                          ctypes.byref(mod_info)):
                                    mod_name = mod_info.ModuleName.decode(
                                        "utf-8", errors="ignore")
                                    mod_base = mod_info.BaseOfImage
                                    resolved = _resolve_export(mod_base, pc)
                                    if resolved:
                                        fname, foffset = resolved
                                        frames.append(
                                            f"{fname}+0x{foffset:x}  [{pc:#x}]")
                                    else:
                                        frames.append(
                                            f"{mod_name}+0x{pc - mod_base:x}  [{pc:#x}]")
                                else:
                                    mod = dbg.SymGetModuleBase64(hProcess, pc)
                                    if mod:
                                        frames.append(f"<unknown>+0x{pc - mod:x}  [{pc:#x}]")
                                    else:
                                        frames.append(f"[{pc:#x}]")
                    else:
                        frames = ["[GetThreadContext failed]"]

                    threads_out.append({"header": f"Thread {tid}", "frames": frames})
                finally:
                    k32.ResumeThread(hThread)
                    k32.CloseHandle(hThread)

            dbg.SymCleanup(hProcess)
            if threads_out:
                return {"method": "dbghelp", "raw": "", "threads": threads_out}
            return None
        finally:
            k32.CloseHandle(hProcess)
    except Exception:
        return None


# ── psutil fallback ───────────────────────────────────────────────────────────

def _psutil_fallback(proc):
    try:
        threads = proc.threads()
        return {
            "method": "psutil-threads",
            "raw": "",
            "threads": [
                {
                    "header": f"Thread {t.id}  (user={t.user_time:.3f}s  sys={t.system_time:.3f}s)",
                    "frames": ["[No debugger available — stack frames not captured]"],
                }
                for t in threads
            ],
        }
    except (psutil.AccessDenied, psutil.NoSuchProcess):
        return {"method": "none", "raw": "", "threads": []}


# ── main entry ────────────────────────────────────────────────────────────────

def _is_python_exe(exe):
    if not exe:
        return False
    return "python" in os.path.basename(exe).lower()


def _get_traces(pid, exe):
    # Python-specific: py-spy first
    if _is_python_exe(exe):
        r = _try_pyspy(pid)
        if r:
            return r

    if _SYS == "Windows":
        r = _try_cdb(pid)
        if r:
            return r
        r = _try_dbghelp_windows(pid)
        if r:
            return r
        # py-spy works on any process on Windows too
        r = _try_pyspy(pid)
        if r:
            return r
    elif _SYS == "Darwin":
        r = _try_lldb(pid)
        if r:
            return r
    elif _SYS == "Linux":
        r = _try_gdb(pid)
        if r:
            return r

    return None


def collect_dump(target):
    """
    Collect a stack dump for the given process.

    Args:
        target: PID (int or numeric string) or process name string.

    Returns:
        dict with process metadata and stack trace info.
    """
    proc = _find_process(target)
    if proc is None:
        return {"error": f"No process found matching: {target}"}

    try:
        info = {
            "pid":         proc.pid,
            "name":        _safe(proc.name) or "?",
            "status":      _safe(proc.status) or "unknown",
            "exe":         _safe(proc.exe),
            "cmdline":     _safe(lambda: " ".join(proc.cmdline())),
            "username":    _safe(proc.username),
            "num_threads": _safe(proc.num_threads) or 0,
        }
    except (psutil.NoSuchProcess, psutil.AccessDenied) as exc:
        return {"error": str(exc)}

    trace = _get_traces(proc.pid, info.get("exe") or "")
    if trace is None:
        trace = _psutil_fallback(proc)

    info.update(trace)
    return info
