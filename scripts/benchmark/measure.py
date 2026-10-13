"""Wall-clock time and peak memory of a command and all its child processes (Windows).

Method:
- The command is started suspended (CREATE_SUSPENDED), assigned to a fresh Job Object,
  then resumed. Child processes (e.g. python.exe started by the data-clean.exe launcher)
  are automatically members of the job.
- Time: time.perf_counter() from just before process creation to process exit.
- Peak committed private memory: JOBOBJECT_EXTENDED_LIMIT_INFORMATION.PeakProcessMemoryUsed
  (largest single process) and PeakJobMemoryUsed (all processes together), maintained by the
  kernel, so no sampling is involved.
- Peak working set (physical memory): a thread polls the job's process list every 5 ms and
  opens a handle to each new process; after exit, GetProcessMemoryInfo(handle).PeakWorkingSetSize
  is read from the still-open handle.

Run this file directly to calibrate the method: it starts processes that allocate a known
amount of memory (0, 200 and 800 MiB, and 500 MiB through a cmd.exe launcher) and prints
what was measured.
"""
import ctypes
import subprocess
import sys
import threading
import time

if sys.platform != "win32":
    raise SystemExit("measure.py uses the Windows Job Object API and only runs on Windows.")

import ctypes.wintypes as wt  # noqa: E402  (Windows-only module)

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
ntdll = ctypes.WinDLL("ntdll")
CREATE_SUSPENDED = 0x00000004
JobObjectBasicProcessIdList = 3
JobObjectExtendedLimitInformation = 9
PROCESS_QUERY_INFORMATION, PROCESS_VM_READ, SYNCHRONIZE = 0x0400, 0x0010, 0x00100000


class IO_COUNTERS(ctypes.Structure):
    _fields_ = [(n, ctypes.c_ulonglong) for n in ("Read", "Write", "Other", "ReadT", "WriteT", "OtherT")]


class BASIC_LIMIT(ctypes.Structure):
    _fields_ = [("PerProcessUserTimeLimit", ctypes.c_longlong), ("PerJobUserTimeLimit", ctypes.c_longlong),
                ("LimitFlags", wt.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t), ("MaximumWorkingSetSize", ctypes.c_size_t),
                ("ActiveProcessLimit", wt.DWORD), ("Affinity", ctypes.c_size_t), ("PriorityClass", wt.DWORD), ("SchedulingClass", wt.DWORD)]


class EXTENDED_LIMIT(ctypes.Structure):
    _fields_ = [("Basic", BASIC_LIMIT), ("Io", IO_COUNTERS), ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t), ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]


class PID_LIST(ctypes.Structure):
    _fields_ = [("Assigned", wt.DWORD), ("InList", wt.DWORD), ("Ids", ctypes.c_size_t * 64)]


class PMC(ctypes.Structure):
    _fields_ = [("cb", wt.DWORD), ("PageFaultCount", wt.DWORD), ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t), ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t), ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t), ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]


kernel32.CreateJobObjectW.restype = wt.HANDLE
kernel32.OpenProcess.restype = wt.HANDLE


def _check(ok, what):
    if not ok:
        raise ctypes.WinError(ctypes.get_last_error(), what)


def run_measured(cmd, cwd=None, stdout=None, stderr=None, env=None):
    job = kernel32.CreateJobObjectW(None, None)
    _check(job, "CreateJobObject")
    start = time.perf_counter()
    proc = subprocess.Popen(cmd, cwd=cwd, stdout=stdout, stderr=stderr, env=env, creationflags=CREATE_SUSPENDED)
    _check(kernel32.AssignProcessToJobObject(job, wt.HANDLE(int(proc._handle))), "AssignProcessToJobObject")
    handles, stop = {}, threading.Event()

    def poll():
        while not stop.is_set():
            pids = PID_LIST()
            if kernel32.QueryInformationJobObject(job, JobObjectBasicProcessIdList, ctypes.byref(pids), ctypes.sizeof(pids), None):
                for pid in pids.Ids[: pids.InList]:
                    if pid and pid not in handles:
                        h = kernel32.OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ | SYNCHRONIZE, False, int(pid))
                        if h:
                            handles[pid] = h
            time.sleep(0.005)

    poller = threading.Thread(target=poll, daemon=True)
    poller.start()
    ntdll.NtResumeProcess(wt.HANDLE(int(proc._handle)))
    exit_code = proc.wait()
    wall = time.perf_counter() - start
    stop.set()
    poller.join()
    info = EXTENDED_LIMIT()
    _check(kernel32.QueryInformationJobObject(job, JobObjectExtendedLimitInformation, ctypes.byref(info), ctypes.sizeof(info), None), "QueryInformationJobObject")
    peak_ws = {}
    for pid, h in handles.items():
        pmc = PMC()
        pmc.cb = ctypes.sizeof(PMC)
        if kernel32.K32GetProcessMemoryInfo(wt.HANDLE(h), ctypes.byref(pmc), pmc.cb):
            peak_ws[str(pid)] = pmc.PeakWorkingSetSize
        kernel32.CloseHandle(wt.HANDLE(h))
    kernel32.CloseHandle(wt.HANDLE(job))
    return {
        "exit_code": exit_code,
        "wall_seconds": wall,
        "peak_process_commit_bytes": info.PeakProcessMemoryUsed,
        "peak_job_commit_bytes": info.PeakJobMemoryUsed,
        "peak_working_set_bytes_by_process": peak_ws,
        "processes_seen": len(peak_ws),
    }


if __name__ == "__main__":  # calibration: processes that allocate a known amount
    import json

    for mb in (0, 200, 800):
        code = f"b = bytearray({mb} * 1024 * 1024); b[::4096] = b'x' * len(b[::4096])"
        result = run_measured([sys.executable, "-c", code])
        print(json.dumps({"allocated_MiB": mb, "wall_s": round(result["wall_seconds"], 3),
                          "peak_process_commit_MiB": round(result["peak_process_commit_bytes"] / 2**20, 1),
                          "peak_ws_MiB": {k: round(v / 2**20, 1) for k, v in result["peak_working_set_bytes_by_process"].items()}}))
    # through a launcher: cmd.exe -> python.exe (child must be captured too)
    result = run_measured(["cmd.exe", "/c", sys.executable, "-c", "b = bytearray(500 * 1024 * 1024); b[::4096] = b'x' * len(b[::4096])"])
    print(json.dumps({"via_launcher_allocated_MiB": 500, "processes": result["processes_seen"],
                      "peak_process_commit_MiB": round(result["peak_process_commit_bytes"] / 2**20, 1),
                      "peak_job_commit_MiB": round(result["peak_job_commit_bytes"] / 2**20, 1),
                      "peak_ws_MiB": {k: round(v / 2**20, 1) for k, v in result["peak_working_set_bytes_by_process"].items()}}))
