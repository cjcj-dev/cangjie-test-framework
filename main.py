import os, sys
from pathlib import Path

if __name__ == "__main__":
    entry = str(Path(__file__).with_name("upstream-main.py").resolve())
    if sys.platform != "linux":
        import runpy
        runpy.run_path(entry, run_name="__main__")
        sys.exit(0)
    # Use the same interpreter flags that Python propagates to its workers.
    from subprocess import _args_from_interpreter_flags
    uid, gid = os.geteuid(), os.getegid()
    before = os.readlink("/proc/self/ns/uts")
    options = [] if uid == 0 else ["--map-current-user"]
    print(f"MAPLE_UTS: requesting a private UTS for uid={uid}", file=sys.stderr, flush=True)
    try:
        os.execvp("unshare", ["unshare", "--uts", *options, "--", sys.executable,
                             "-I", "-S", "-c", "import os, pwd, sys\nfrom pathlib import Path\n\nbefore, uid, gid = sys.argv[1:4]\nafter = os.readlink(\"/proc/self/ns/uts\")\nif before == after or (os.geteuid(), os.getegid()) != (int(uid), int(gid)):\n    sys.exit(\"MAPLE_UTS: namespace did not change or credentials changed; refusing workload\")\ncaps = next(line.split()[1] for line in Path(\"/proc/self/status\").read_text().splitlines()\n            if line.startswith(\"CapEff:\"))\ncan_set_hostname = bool(int(caps, 16) & (1 << 21))  # CAP_SYS_ADMIN\naccount = pwd.getpwuid(os.geteuid()).pw_name\nif can_set_hostname != (os.geteuid() == 0) or (account == \"root\") != (os.geteuid() == 0):\n    sys.exit(\"MAPLE_UTS: hostname privilege does not match the test account; refusing workload\")\nos.environ[\"USER\"] = account\nprint(f\"MAPLE_UTS: parent={before} child={after} uid={uid} gid={gid} user={account}\", flush=True)\nos.execv(sys.executable, [sys.executable, *sys.argv[4:]])\n", before, str(uid), str(gid),
                             *_args_from_interpreter_flags(), entry, *sys.argv[1:]])
    except OSError as error:
        sys.exit(f"MAPLE_UTS: cannot launch unshare: {error}")
