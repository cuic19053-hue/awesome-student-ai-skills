"""Bounded, server-only background reconciliation. No guessed charge or refund."""
import json
import os
import time
import urllib.error
import urllib.request

from .billing_diagnostics import UsageOnlyClient, inspect_receipt
from .supabase_http import supabase_urlopen
from .wopally_client import WopallyUnavailable


def worker_rpc(store, action, args=None):
    backend_secret = os.environ.get("WORKBENCH_BACKEND_SECRET", "")
    worker_secret = os.environ.get("BILLING_DIAGNOSTIC_TOKEN", "")
    if not backend_secret or not worker_secret or not hasattr(store, "project_url"):
        raise RuntimeError("Reconciliation worker is not configured")
    payload = {
        "p_backend_secret": backend_secret, "p_worker_secret": worker_secret,
        "p_action": action, "p_args": args or {},
    }
    request = urllib.request.Request(
        store.project_url + "/rest/v1/rpc/billing_reconciliation_worker",
        data=json.dumps(payload).encode(), method="POST",
        headers={"apikey": store.publishable_key, "Authorization": "Bearer " + store.publishable_key,
                 "Content-Type": "application/json"},
    )
    try:
        with supabase_urlopen(request, timeout=4) as response:
            data = json.load(response)
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        raise RuntimeError("Reconciliation ledger unavailable") from exc
    if not isinstance(data, dict):
        raise RuntimeError("Invalid reconciliation ledger response")
    return data


def run_once(store, rpc=worker_rpc, lookup=inspect_receipt):
    """Claim at most one job: repeated/concurrent runs are fenced by its lease."""
    job = rpc(store, "claim")
    outcome = "idle"
    if job.get("status") == "claimed":
        args = {"request_id": job["request_id"], "lease_id": job["lease_id"]}
        try:
            key_id = int(job.get("api_key_id") or 0)
            if key_id <= 0:
                reason = "invalid_key"
            else:
                receipt = lookup(job["request_id"], key_id)
                reason = receipt["status"]
                if reason == "confirmed":
                    if receipt["model"] != job["model"]:
                        reason = "model_mismatch"
                    else:
                        result = rpc(store, "complete", {
                            **args, "actual_micro_cny": receipt["actual_micro_cny"],
                            "provider_request_id": receipt["provider_request_id"],
                        })
                        outcome = result["status"]
                        reason = None
        except (WopallyUnavailable, ValueError, TypeError, KeyError):
            reason = "provider_unavailable"
        if reason is not None:
            result = rpc(store, "defer", {**args, "reason": reason})
            outcome = result["status"]
    elif job.get("status") != "idle":
        raise RuntimeError("Invalid reconciliation claim response")
    alerts = rpc(store, "alerts")
    count = alerts.get("alert_count")
    if type(count) is not int or count < 0:
        raise RuntimeError("Invalid reconciliation alert response")
    # Do not return request identifiers, user information or upstream data.
    return {"status": outcome, "alert_count": count}


def run_batch(store, rpc=worker_rpc, clock=time.monotonic):
    """At most five claims, with a conservative budget for Vercel's 60s limit."""
    started = clock()
    total_alerts = 0
    processed = 0
    outcome = "idle"
    client = UsageOnlyClient(timeout=3)
    for _ in range(5):
        # One remaining provider lookup may take five 3s pages + login timeout.
        if processed and clock() - started >= 15:
            break
        result = run_once(store, rpc, lambda request_id, key_id: inspect_receipt(
            request_id, key_id, client
        ))
        outcome = result["status"]
        total_alerts += result["alert_count"]
        if outcome == "idle":
            break
        processed += 1
    return {"status": outcome, "processed": processed, "alert_count": total_alerts}
