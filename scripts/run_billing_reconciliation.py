"""Scheduled, secret-authenticated trigger; never prints the token or user data."""
import json
import os
import sys
import urllib.error
import urllib.request


def main():
    token = os.environ.get("BILLING_RECONCILIATION_TOKEN", "")
    if not token:
        print("Billing reconciliation secret missing", file=sys.stderr)
        return 1
    request = urllib.request.Request(
        "https://agent.stardust.website/api/admin/reconcile-usage", data=b"{}",
        headers={
            "x-billing-probe-token": token,
            "Content-Type": "application/json",
            "User-Agent": "StardustBillingReconciler/1.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=58) as response:
            result = json.load(response)
    except urllib.error.HTTPError as exc:
        print(f"Billing reconciliation endpoint returned HTTP {exc.code}", file=sys.stderr)
        return 1
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        print("Billing reconciliation endpoint unavailable", file=sys.stderr)
        return 1
    if result.get("status") not in ("idle", "settled", "needs_review", "deferred",
                                     "already_resolved", "lease_expired"):
        print("Unexpected billing reconciliation result", file=sys.stderr)
        return 1
    count = result.get("alert_count")
    if type(count) is not int or count < 0:
        print("Invalid billing reconciliation alert result", file=sys.stderr)
        return 1
    print(f"Billing reconciliation: {result['status']}; new overdue alerts: {count}")
    if count:
        print("::error::Billing records need operator review; inspect the protected billing diagnostics.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
