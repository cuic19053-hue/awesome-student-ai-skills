"""Bounded, server-only background reconciliation. No guessed charge or refund."""
import json
import hashlib
import hmac
import os
import re
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
    payload = {"p_backend_secret": backend_secret, "p_worker_secret": worker_secret}
    if action == "configure_scheduler":
        function = "billing_reconciliation_scheduler"
    elif action == "scheduler_tick":
        function = "billing_reconciliation_scheduler_tick"
        payload["p_timestamp"] = (args or {})["timestamp"]
    else:
        function = "billing_reconciliation_worker"
        payload.update(p_action=action, p_args=args or {})
    request = urllib.request.Request(
        store.project_url + "/rest/v1/rpc/" + function,
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


def verify_scheduler_tick(timestamp, signature, secret, now=None):
    """Accept only a short-lived, minute-aligned HMAC; database fences replay."""
    if not re.fullmatch(r"[0-9]{10}", timestamp or "") or not re.fullmatch(
        r"[a-f0-9]{64}", signature or ""
    ):
        return False
    tick = int(timestamp)
    current = time.time() if now is None else now
    if tick % 60 or not -10 <= current - tick <= 90:
        return False
    digest = hmac.new(secret.encode(), f"stardust-billing-tick:{timestamp}".encode(),
                      hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature, digest)


def run_once(store, rpc=worker_rpc, lookup=inspect_receipt, *, include_alerts=True):
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
    count = rpc(store, "alerts").get("alert_count") if include_alerts else 0
    if type(count) is not int or count < 0:
        raise RuntimeError("Invalid reconciliation alert response")
    # Do not return request identifiers, user information or upstream data.
    return {"status": outcome, "alert_count": count}


def run_batch(store, rpc=worker_rpc, clock=time.monotonic, *, include_alerts=True):
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
        ), include_alerts=include_alerts)
        outcome = result["status"]
        total_alerts += result["alert_count"]
        if outcome == "idle":
            break
        processed += 1
    return {"status": outcome, "processed": processed, "alert_count": total_alerts}
