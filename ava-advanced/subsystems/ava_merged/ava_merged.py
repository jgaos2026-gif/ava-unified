"""AVA Merged — one launcher for the full merged system.

This is the MERGED package (2026-11-03): the corrected NextGen
FastAPI services PLUS the combined stdlib services that NextGen
did not rewrite. One service per port, no conflicts:

  8772 voice_bridge            (stdlib, from ava-combined)
  8773 brain_bridge            (FastAPI, NextGen corrected)
  8774 stitch_bridge           (stdlib, from ava-combined)
  8775 sovereign_orchestrator  (FastAPI, NextGen corrected)
  8776 private_vault           (FastAPI, NextGen corrected, PIN-derived key)
  8780 local_organism_core     (stdlib, from ava-combined)
  8781 embedding_braid         (FastAPI, NextGen corrected, token-hash)
  8782 tool_sandbox            (stdlib, from ava-combined)
  on-demand: quant_benchmark, performance_governor (stdlib)

Run:  python ava_merged.py
List: python ava_merged.py --list

SECURITY: no PIN hash, no secret, no default secret anywhere in this
package. Set AVA_VAULT_PIN_HASH in the environment only; if unset,
the vault stays locked (503). The stdlib vault from ava-combined is
NOT included — the NextGen vault replaces it, because the old vault
carried an exposed PIN hash.
"""
import asyncio
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PROCS = []  # every child process started, for shutdown cleanup
# (name, port, kind, target) — kind "uvicorn" = FastAPI module, "python" = stdlib script
SERVICES = [
    ("voice_bridge", 8772, "python", "services_stdlib/voice_bridge.py"),
    ("brain_bridge", 8773, "uvicorn", "services.brain_bridge:app"),
    ("stitch_bridge", 8774, "python", "services_stdlib/stitch_bridge.py"),
    ("sovereign_orchestrator", 8775, "uvicorn", "services.sovereign_orchestrator:app"),
    ("private_vault", 8776, "uvicorn", "services.private_vault:app"),
    ("local_organism_core", 8780, "python", "services_stdlib/local_organism_core.py"),
    ("embedding_braid", 8781, "uvicorn", "services.embedding_braid:app"),
    ("tool_sandbox", 8782, "python", "services_stdlib/tool_sandbox.py"),
]


async def run_service(name, port, kind, target):
    delay = 2.0
    while True:
        print(f"[Launcher] Starting {name} on 127.0.0.1:{port}", flush=True)
        if kind == "uvicorn":
            cmd = [sys.executable, "-m", "uvicorn", target,
                   "--host", "127.0.0.1", "--port", str(port),
                   "--log-level", "error"]
        else:
            cmd = [sys.executable, os.path.join(HERE, target)]
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT, cwd=HERE)
        PROCS.append(proc)

        async def _drain():
            while True:
                line = await proc.stdout.readline()
                if not line:
                    break
                print(f"[{name}] {line.decode().strip()}", flush=True)
        drain = asyncio.create_task(_drain())
        try:
            code = await proc.wait()
        except asyncio.CancelledError:
            # Launcher is stopping: terminate the child, don't orphan it.
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), timeout=5)
            except Exception:
                proc.kill()
            drain.cancel()
            raise
        drain.cancel()
        print(f"[Launcher] {name} exited with code {code}; "
              f"restarting in {delay:.0f}s", flush=True)
        await asyncio.sleep(delay)
        delay = min(delay * 2, 30.0)


async def main(argv):
    if "--list" in argv:
        for name, port, kind, target in SERVICES:
            print(f"{name:25s} 127.0.0.1:{port}  [{kind}] {target}")
        print("on-demand (no server): services_stdlib/quant_benchmark.py, "
              "services_stdlib/performance_governor.py")
        return 0
    if not os.environ.get("AVA_VAULT_PIN_HASH"):
        print("[Launcher] WARNING: AVA_VAULT_PIN_HASH is not set — "
              "the vault will stay locked until you set it. "
              "No default value is used.", flush=True)
    import signal as _signal
    shutdown = asyncio.Event()
    loop = asyncio.get_running_loop()
    for _sig in (_signal.SIGINT, _signal.SIGTERM):
        try:
            loop.add_signal_handler(_sig, shutdown.set)
        except (NotImplementedError, ValueError):
            pass
    tasks = [asyncio.create_task(run_service(n, p, k, t))
             for n, p, k, t in SERVICES]
    print("All merged AVA services running. Ctrl-C stops them all.", flush=True)
    await shutdown.wait()
    print("[Launcher] Shutdown requested — stopping all services...", flush=True)
    for proc in PROCS:
        try:
            if proc.returncode is None:
                proc.terminate()
        except Exception:
            pass
    await asyncio.sleep(2)
    for proc in PROCS:
        try:
            if proc.returncode is None:
                proc.kill()
        except Exception:
            pass
    for t in tasks:
        t.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    return 0


def _kill_all_children():
    """Terminate any child still alive after the loop exits. This is
    the deterministic shutdown path — task cancellation alone left
    children orphaned in testing, so this runs in __main__'s finally."""
    for proc in PROCS:
        try:
            if proc.returncode is None:
                proc.terminate()
        except Exception:
            pass
    import time as _time
    _time.sleep(2)
    for proc in PROCS:
        try:
            if proc.returncode is None:
                proc.kill()
        except Exception:
            pass


if __name__ == "__main__":
    try:
        asyncio.run(main(sys.argv[1:]))
    except KeyboardInterrupt:
        print("\nLauncher stopped.")
    finally:
        _kill_all_children()
