# Static knowledge base for Windows Event IDs and heuristic findings.
# concern levels: ignore | monitor | investigate | fix_now

WINDOWS_EVENT_KB: dict[int, dict] = {

    # --- Disk / Storage ---
    7: {
        "title": "Bad Block Detected",
        "explanation": "The disk controller found an unreadable sector. Windows attempted recovery but this is an early sign of physical drive failure.",
        "concern": "fix_now",
        "action": "Back up your data immediately, then run 'chkdsk /r' on the affected drive. Replace the drive if SMART data shows reallocated sectors.",
    },
    11: {
        "title": "Disk Controller Error",
        "explanation": "A disk or USB controller reported a hardware error, often caused by a failing drive, loose cable, or faulty controller.",
        "concern": "investigate",
        "action": "Check SMART data with CrystalDiskInfo. Re-seat SATA/power cables. Replace the drive if SMART shows deteriorating attributes.",
    },
    15: {
        "title": "Device Not Ready",
        "explanation": "A storage device was not ready when Windows tried to access it — could be a failing drive or intermittent connection.",
        "concern": "investigate",
        "action": "Verify the drive is properly connected. Run a SMART health check. If it's an external drive, try a different cable or port.",
    },
    51: {
        "title": "Disk Error During Paging Operation",
        "explanation": "Windows encountered an error reading or writing virtual memory (swap) on disk. Usually indicates drive trouble.",
        "concern": "fix_now",
        "action": "Run 'chkdsk /r' immediately. Back up data — if this recurs, the drive is likely failing.",
    },
    55: {
        "title": "NTFS File System Corruption",
        "explanation": "The NTFS driver detected corruption on a volume. Data integrity may be at risk.",
        "concern": "fix_now",
        "action": "Run 'chkdsk /f' on the affected drive. If corruption keeps returning, the underlying hardware may be faulty.",
    },
    129: {
        "title": "Storage Controller Reset (Timeout Recovery)",
        "explanation": "A storage device stopped responding and Windows forced a controller reset. A single occurrence may be benign; repeated events are concerning.",
        "concern": "investigate",
        "action": "Check SMART data. Update storage controller drivers or firmware. Frequent resets suggest a dying drive.",
    },
    153: {
        "title": "Disk I/O Retried",
        "explanation": "Windows had to retry a disk I/O operation, suggesting marginal drive health or a transient error.",
        "concern": "monitor",
        "action": "Monitor SMART attributes over the next few days. If retry counts increase, plan for drive replacement.",
    },
    157: {
        "title": "Disk Surprise Removal",
        "explanation": "A disk was removed while Windows was actively using it — could corrupt data.",
        "concern": "investigate",
        "action": "Ensure internal drive cables are secure. If external, always use 'Safely Remove Hardware' before disconnecting.",
    },

    # --- Application Crashes ---
    1000: {
        "title": "Application Crash",
        "explanation": "A Windows application crashed with an unhandled exception. The faulting module in the event details tells you where it broke.",
        "concern": "investigate",
        "action": "Identify the crashing app and module from the event message. Update or reinstall the application. Search online for the faulting module name.",
    },
    1001: {
        "title": "Windows Error Reporting Collected",
        "explanation": "Windows Error Reporting logged a crash dump from a previous crash (pairs with Event 1000 or 41).",
        "concern": "monitor",
        "action": "Find the matching Event 1000 to identify the crashing application and take action there.",
    },
    1002: {
        "title": "Application Hang",
        "explanation": "A Windows application stopped responding and had to be terminated.",
        "concern": "investigate",
        "action": "Identify the hung app. Check system resources (disk I/O, RAM) at the time. Update the application and check for known bugs.",
    },
    1026: {
        "title": ".NET Runtime Error",
        "explanation": "A .NET application threw an unhandled exception and crashed. The exception type in the message indicates the root cause.",
        "concern": "investigate",
        "action": "Note the exception type and faulting application. Update .NET runtime and the affected application.",
    },

    # --- Service Control Manager ---
    7022: {
        "title": "Service Hung on Start",
        "explanation": "A service started but never signaled it was ready, causing Windows to give up waiting.",
        "concern": "investigate",
        "action": "Identify the service from the event. Restart it manually via Services.msc. Check if its dependencies are running.",
    },
    7023: {
        "title": "Service Terminated with Error",
        "explanation": "A Windows service stopped due to an error. The error code in the message points to the cause.",
        "concern": "investigate",
        "action": "Note the error code and service name. Search online for that specific error code + service combination.",
    },
    7024: {
        "title": "Service Terminated (Service-Specific Error)",
        "explanation": "A service exited with a service-specific error code, typically indicating misconfiguration or a missing resource.",
        "concern": "investigate",
        "action": "Look up the service-specific error code in the event. Common causes: missing DLLs, wrong credentials, or port conflicts.",
    },
    7031: {
        "title": "Service Crashed and Will Restart",
        "explanation": "A service terminated unexpectedly and Windows will attempt to restart it per its recovery settings.",
        "concern": "investigate",
        "action": "Identify which service crashed. If it recurs, check the application event log for related errors and consider reinstalling the software.",
    },
    7034: {
        "title": "Service Crashed Unexpectedly",
        "explanation": "A service terminated without a clean shutdown signal and no restart is configured.",
        "concern": "investigate",
        "action": "Restart the service manually via Services.msc. If recurring, update or reinstall the associated software.",
    },
    7038: {
        "title": "Service Failed to Log On",
        "explanation": "A service could not authenticate with the configured user account — usually a changed password or revoked permission.",
        "concern": "fix_now",
        "action": "Open Services.msc, find the service, and update its logon credentials. Grant 'Log on as a service' rights if needed.",
    },

    # --- System / Kernel ---
    41: {
        "title": "Kernel Power — Unexpected Shutdown",
        "explanation": "The system shut down without going through a clean shutdown sequence — caused by a crash (BSOD), power loss, or hard reset.",
        "concern": "investigate",
        "action": "Check for BSOD minidumps in C:\\Windows\\Minidump using WhoCrashed or WinDbg. Test RAM with MemTest86. Verify PSU stability.",
    },
    6008: {
        "title": "Previous Shutdown Was Unexpected",
        "explanation": "Windows recorded on boot that the previous session ended without a clean shutdown (companion to Event 41).",
        "concern": "monitor",
        "action": "Correlate with Event 41. An isolated incident may be a power outage; recurring events suggest hardware instability.",
    },
    219: {
        "title": "Driver Failed to Load",
        "explanation": "Windows could not load a device driver during startup, which may leave a device non-functional.",
        "concern": "investigate",
        "action": "Identify the failed driver from the event. Update or reinstall it via Device Manager. Check for a yellow warning icon there.",
    },
    10010: {
        "title": "DCOM Server Timeout",
        "explanation": "A DCOM (Component Object Model) server did not respond in time. Often harmless but can indicate hung background processes.",
        "concern": "monitor",
        "action": "If infrequent, ignore it. If frequent, identify the CLSID in the message via regedit to find the component and update or disable it.",
    },

    # --- Windows Update ---
    20: {
        "title": "Windows Update Failed to Install",
        "explanation": "A Windows Update package could not be installed successfully.",
        "concern": "investigate",
        "action": "Run 'sfc /scannow' and then 'DISM /Online /Cleanup-Image /RestoreHealth'. Run Windows Update troubleshooter from Settings.",
    },

    # --- Network ---
    4201: {
        "title": "Network Adapter Connected",
        "explanation": "A network adapter established a connection — normal on boot or after reconnecting.",
        "concern": "ignore",
        "action": "No action needed. If unexpected, verify no unauthorized network changes were made.",
    },
    4202: {
        "title": "Network Adapter Disconnected",
        "explanation": "A network interface dropped its connection. Frequent disconnects indicate a driver, cable, or hardware problem.",
        "concern": "monitor",
        "action": "Update network adapter drivers. Check cable integrity. On Wi-Fi, try a different channel or move closer to the router.",
    },
    4226: {
        "title": "TCP/IP Half-Open Connection Limit Reached",
        "explanation": "Windows hit its limit for simultaneous half-open TCP connections. May indicate a network scanner, worm, or P2P software.",
        "concern": "monitor",
        "action": "Check for unusual outbound connections in Resource Monitor. If unexpected, scan for malware.",
    },

    # --- Security ---
    4625: {
        "title": "Failed Login Attempt",
        "explanation": "A logon attempt was made with invalid credentials. Isolated failures are normal; high volumes may indicate a brute-force attack.",
        "concern": "monitor",
        "action": "Check the account name in the event. If automated/external attempts are detected, review firewall rules and account lockout policies.",
    },
    4720: {
        "title": "User Account Created",
        "explanation": "A new local user account was created on this machine.",
        "concern": "investigate",
        "action": "Verify this was intentional. Unauthorized account creation is a significant security red flag.",
    },
    4732: {
        "title": "User Added to Security Group",
        "explanation": "A user was added to a local security group. Adding users to Administrators is especially high-risk.",
        "concern": "investigate",
        "action": "Confirm the account and group in the event details are expected. Immediately investigate if the Administrators group was modified without authorization.",
    },

    # --- Windows Defender ---
    1116: {
        "title": "Malware Detected",
        "explanation": "Windows Defender found malware or a potentially unwanted application on this system.",
        "concern": "fix_now",
        "action": "Open Windows Security and review the threat. Run a full scan. If the threat was not fully removed, use the Malicious Software Removal Tool (MRT).",
    },
    1117: {
        "title": "Malware — Action Taken",
        "explanation": "Windows Defender took action (quarantine/remove) against a detected threat.",
        "concern": "investigate",
        "action": "Confirm in Windows Security that the threat was successfully remediated. Run a full scan to check for any persistence mechanisms.",
    },

    # --- Reliability ---
    1530: {
        "title": "Windows Profile Not Fully Saved",
        "explanation": "Registry files were still in use when Windows tried to save your user profile at shutdown — some settings may not have been saved.",
        "concern": "monitor",
        "action": "Usually harmless. If recurring, check for processes that don't exit cleanly on shutdown.",
    },
    1008: {
        "title": "Performance Counter Load Failure",
        "explanation": "A performance counter library failed to load, which may affect monitoring tools but not normal system operation.",
        "concern": "monitor",
        "action": "Run 'lodctr /r' in an elevated command prompt to rebuild performance counters.",
    },

    # --- HAL (very common, low severity) ---
    20: {  # HAL Event ID 20 — overrides Windows Update 20 if provider matches HAL
        "title": "HAL ACPI Timing Warning",
        "explanation": "The Hardware Abstraction Layer detected an ACPI timing discrepancy. Extremely common on modern hardware and almost always harmless.",
        "concern": "ignore",
        "action": "No action needed. A BIOS/UEFI firmware update may reduce the frequency if it bothers you.",
    },
    21: {
        "title": "HAL ACPI Timing Warning",
        "explanation": "An ACPI timing anomaly logged by the HAL — nearly identical to Event 20. Very common and rarely indicates a real problem.",
        "concern": "ignore",
        "action": "No action needed unless you're experiencing actual system instability alongside this event.",
    },
}


HEURISTIC_KB: dict[str, dict] = {
    "disk_full_critical": {
        "explanation": "This partition is critically full. The OS needs free space for logs, temp files, and virtual memory — running out can cause crashes and data loss.",
        "concern": "fix_now",
        "action": "Free up space immediately: empty Recycle Bin, run Disk Cleanup, uninstall unused apps, or move large files to another drive.",
        "source": "static",
    },
    "disk_full_warning": {
        "explanation": "Disk usage is elevated. Performance degrades as free space shrinks, and writes will fail if the drive fills completely.",
        "concern": "investigate",
        "action": "Use WinDirStat (Windows) or DaisyDisk (macOS) to find large files. Aim to keep at least 10–15% free.",
        "source": "static",
    },
    "ram_critical": {
        "explanation": "RAM is nearly exhausted. The OS is likely swapping heavily to disk, causing severe slowdowns and potential instability.",
        "concern": "fix_now",
        "action": "Close memory-heavy applications immediately. If this is recurring, consider adding more RAM or limiting startup programs.",
        "source": "static",
    },
    "ram_warning": {
        "explanation": "RAM usage is elevated. The system may begin swapping to disk soon, which significantly degrades performance.",
        "concern": "monitor",
        "action": "Monitor which applications consume the most memory via Task Manager. Close unused browser tabs and background apps.",
        "source": "static",
    },
    "network_errors": {
        "explanation": "The network interface has accumulated a significant number of transmission errors since boot, suggesting driver or hardware issues.",
        "concern": "investigate",
        "action": "Update network adapter drivers. Check cable integrity. On Wi-Fi, move closer to the router or try switching Wi-Fi channels.",
        "source": "static",
    },
    "cpu_hog": {
        "explanation": "A single process is consuming an unusually high share of CPU, which may cause system-wide slowdowns.",
        "concern": "investigate",
        "action": "Identify the process in Task Manager. If unexpected, investigate it — it may be a runaway background task or malware. Legitimate tasks (antivirus, updates) may be temporary.",
        "source": "static",
    },
}
