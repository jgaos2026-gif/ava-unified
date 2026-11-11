"""AVA NextGen gateway — deliberately NOT named main.py.

The pasted version shipped a main.py that would overwrite Brick 1's
job CLI (~/workspace/your_files/jga-full-auto/main.py) if copied into
that folder. This entry point lives in the NextGen package under its
own name, so the two systems cannot collide.

Usage:
  python gateway.py --demo          # real 11VT allocator check + one
                                    # orchestrator call (fallback-safe)
  python gateway.py --agent_prompt "your brief"
"""
import argparse
import asyncio
import sys

import httpx

sys.path.insert(0, ".")
from jga_auto.allocator_11vt import allocate_cleared_payment

ORCHESTRATOR_URL = "http://127.0.0.1:8775/orchestrate"


async def run_pipeline(brief: str):
    print("[Gateway] Sending brief to the orchestrator...")
    async with httpx.AsyncClient(trust_env=False) as client:
        try:
            r = await client.post(ORCHESTRATOR_URL,
                                  json={"context_stream": brief}, timeout=15.0)
            data = r.json()
            print("=" * 60)
            print("ORCHESTRATION RESULT")
            print("=" * 60)
            print(f"Vector context injected: {data.get('vector_context_injected')}")
            print(f"Brain fallback (no model): {data.get('brain_fallback')}")
            print(f"Output:\n{data.get('ai_reasoning_output')}")
            print("=" * 60)
        except Exception as e:
            print(f"[Gateway] Orchestrator unreachable: {e}")


def run_demo():
    print("11VT allocator check (real 11-way allocator, receipt-only)...")
    result = allocate_cleared_payment(575000, "DEPOSIT_CLEARED_35", "JOB-TEST")
    assert result["balanced"]
    assert result["banking_execution"] == "NONE_LEDGER_RECEIPT_ONLY"
    vaults = result["vaults"]
    assert len(vaults) == 11, f"expected 11 vaults, got {len(vaults)}"
    assert sum(v["amount_cents"] for v in vaults.values()) == 575000
    print("11VT ALLOCATOR: VERIFIED PASS (11 vaults, balanced, receipt-only)")
    asyncio.run(run_pipeline(
        "Process custom workflow configuration deployment."))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AVA NextGen gateway")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--agent_prompt", type=str)
    args = parser.parse_args()
    if args.demo:
        run_demo()
    elif args.agent_prompt:
        asyncio.run(run_pipeline(args.agent_prompt))
    else:
        parser.print_help()
