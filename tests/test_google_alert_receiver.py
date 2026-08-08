"""Exercise the checked-in Apps Script receiver as code, not source text."""

from __future__ import annotations

import json
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

from tradingagents import operations

ROOT = Path(__file__).resolve().parents[1]
RECEIVER = ROOT / "integrations" / "google_alert_webhook" / "Code.gs"
NODE = shutil.which("node")

HARNESS = textwrap.dedent(
    r"""
    const crypto = require("crypto");
    const fs = require("fs");
    const vm = require("vm");

    const state = {
      now: 10_000_000,
      properties: new Map(),
      quota: 10,
      sent: []
    };

    function receiver() {
      const context = {
        Date: {now() { return state.now; }},
        ContentService: {
          MimeType: {JSON: "application/json"},
          createTextOutput(text) {
            return {text, setMimeType() { return this; }};
          }
        },
        Utilities: {
          DigestAlgorithm: {SHA_256: "sha256"},
          Charset: {UTF_8: "utf8"},
          computeDigest(_algorithm, value) {
            return Array.from(
              crypto.createHash("sha256").update(value, "utf8").digest(),
              byte => byte > 127 ? byte - 256 : byte
            );
          }
        },
        PropertiesService: {
          getScriptProperties() {
            return {
              getProperty(key) { return state.properties.get(key) ?? null; },
              setProperty(key, value) { state.properties.set(key, value); }
            };
          }
        },
        LockService: {
          getScriptLock() {
            return {tryLock() { return true; }, releaseLock() {}};
          }
        },
        MailApp: {
          getRemainingDailyQuota() { return state.quota; },
          sendEmail(to, subject, message) {
            state.sent.push({to, subject, message});
          }
        }
      };
      vm.createContext(context);
      vm.runInContext(fs.readFileSync(process.argv[1], "utf8"), context);
      return context;
    }

    function post(payload) {
      const event = {postData: {contents: JSON.stringify(payload)}};
      return JSON.parse(receiver().doPost(event).text);
    }

    const firstApp = receiver();
    const contractId = vm.runInContext("contractId_()", firstApp);
    const recentReceiptLimit = vm.runInContext("RECENT_RECEIPT_LIMIT", firstApp);
    const nonce = "a".repeat(32);
    const envelope = {schema_version: 1, contract_id: contractId};
    const probe = {...envelope, kind: "probe", nonce};
    const missingRecipientProbe = post(probe);

    state.properties.set("ALERT_EMAIL", "alerts@example.invalid");
    state.quota = 0;
    const exhaustedQuotaProbe = post(probe);
    state.quota = 10;
    const readyProbe = post(probe);

    const coverage = {
      ...envelope,
      kind: "incident",
      idempotency_key: "b".repeat(32),
      component: "collector",
      event: "query_slot_coverage_incomplete",
      severity: "warning"
    };
    const coverageDelivery = post(coverage);
    state.now += 3 * 60 * 60 * 1000;
    const coverageRetryAfterThreeHours = post(coverage);
    const malformedCurrent = post({...coverage, unexpected: true});

    const migratedId = "c".repeat(32);
    state.properties.set(
      "ALERT_RECEIPT_runtime_recovered",
      JSON.stringify({id: migratedId, sent_at_ms: state.now - 3 * 60 * 60 * 1000})
    );
    const migratedDelivery = post({
      ...envelope,
      kind: "recovery",
      idempotency_key: migratedId,
      component: "collector",
      event: "runtime_recovered",
      severity: "info"
    });
    const migratedReceipt = JSON.parse(
      state.properties.get("ALERT_RECEIPT_runtime_recovered")
    );

    function runtimeAlert(id, event = "runtime_unhealthy") {
      const recovered = event === "runtime_recovered";
      return {
        ...envelope,
        kind: recovered ? "recovery" : "incident",
        idempotency_key: id,
        component: "collector",
        event,
        severity: recovered ? "info" : "critical"
      };
    }

    const firstRuntimeAt = state.now;
    const runtimeDelivery = post(runtimeAlert("d".repeat(32)));
    state.now = firstRuntimeAt - 1_000;
    const clockRollbackRuntime = post(runtimeAlert("9".repeat(32)));
    state.now = firstRuntimeAt + 5 * 60 * 1000;
    const throttledRuntime = post(runtimeAlert("e".repeat(32)));
    const throttledReceipt = JSON.parse(
      state.properties.get("ALERT_RECEIPT_runtime_unhealthy")
    );
    state.now += 2 * 60 * 60 * 1000;
    const throttledRetryAfterTwoHours = post(runtimeAlert("e".repeat(32)));
    state.now = firstRuntimeAt + 24 * 60 * 60 * 1000;
    const runtimeReminder = post(runtimeAlert("f".repeat(32)));
    const runtimeRecovery = post(runtimeAlert("1".repeat(32), "runtime_recovered"));

    for (let index = 0; index < recentReceiptLimit + 8; index += 1) {
      const id = index.toString(16).padStart(32, "0");
      post(runtimeAlert(id));
    }
    const boundedRuntimeReceipt = JSON.parse(
      state.properties.get("ALERT_RECEIPT_runtime_unhealthy")
    );

    const legacy = {
      component: "collector",
      event: "x_daily_budget_exhausted",
      severity: "warning",
      details: {message: "UNTRUSTED_DETAIL"}
    };
    const legacyDelivery = post(legacy);
    state.now += 1;
    const legacyDuplicate = post(legacy);
    state.now += 3 * 60 * 60 * 1000;
    const legacyAfterWindow = post(legacy);
    const malformedLegacy = post({...legacy, details: []});
    const legacyProbe = post({
      component: "collector",
      event: "release_preflight_probe",
      severity: "info",
      details: {}
    });

    state.properties.set("ALERT_RECEIPT_delivery_test", "malformed");
    const malformedReceiptDelivery = post({
      ...envelope,
      kind: "test",
      idempotency_key: "2".repeat(32),
      component: "collector",
      event: "delivery_test",
      severity: "info"
    });
    const repairedMalformedReceipt = JSON.parse(
      state.properties.get("ALERT_RECEIPT_delivery_test")
    );

    process.stdout.write(JSON.stringify({
      contractId,
      nonce,
      recentReceiptLimit,
      missingRecipientProbe,
      exhaustedQuotaProbe,
      readyProbe,
      coverageDelivery,
      coverageRetryAfterThreeHours,
      malformedCurrent,
      migratedDelivery,
      migratedReceipt,
      runtimeDelivery,
      clockRollbackRuntime,
      throttledRuntime,
      throttledReceipt,
      throttledRetryAfterTwoHours,
      runtimeReminder,
      runtimeRecovery,
      boundedRuntimeReceipt,
      legacyDelivery,
      legacyDuplicate,
      legacyAfterWindow,
      malformedLegacy,
      legacyProbe,
      malformedReceiptDelivery,
      repairedMalformedReceipt,
      receiptKeys: Array.from(state.properties.keys())
        .filter(key => key.startsWith("ALERT_RECEIPT_"))
        .sort(),
      sent: state.sent
    }));
    """
)


@pytest.mark.unit
@pytest.mark.skipif(NODE is None, reason="Node is required to execute the Apps Script receiver")
def test_google_alert_receiver_behavior() -> None:
    result = subprocess.run(
        [NODE, "-e", HARNESS, str(RECEIVER)],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )
    observed = json.loads(result.stdout)

    assert result.stderr == ""
    assert observed["contractId"] == operations._ALERT_CONTRACT_ID
    assert observed["missingRecipientProbe"]["accepted"] is False
    assert observed["exhaustedQuotaProbe"]["accepted"] is False
    assert observed["readyProbe"] == {
        "schema_version": 1,
        "contract_id": operations._ALERT_CONTRACT_ID,
        "kind": "probe",
        "accepted": True,
        "nonce": observed["nonce"],
    }

    accepted = [
        "coverageDelivery",
        "coverageRetryAfterThreeHours",
        "migratedDelivery",
        "runtimeDelivery",
        "clockRollbackRuntime",
        "throttledRuntime",
        "throttledRetryAfterTwoHours",
        "runtimeReminder",
        "runtimeRecovery",
        "malformedReceiptDelivery",
    ]
    assert all(observed[name]["accepted"] is True for name in accepted)
    assert observed["coverageDelivery"] == observed["coverageRetryAfterThreeHours"]
    assert observed["malformedCurrent"] == {"accepted": False}
    assert observed["malformedLegacy"] == {"accepted": False}
    assert observed["legacyDelivery"] == observed["legacyDuplicate"] == {
        "accepted": True
    }
    assert observed["legacyAfterWindow"] == {"accepted": True}
    assert observed["legacyProbe"] == {"accepted": True}

    assert observed["migratedReceipt"] == {
        "ids": ["c" * 32],
        "last_email_ms": 10_000_000,
    }
    assert "e" * 32 in observed["throttledReceipt"]["ids"]
    assert len(observed["boundedRuntimeReceipt"]["ids"]) == observed[
        "recentReceiptLimit"
    ]
    assert len(observed["repairedMalformedReceipt"]["ids"]) == 1

    subjects = [message["subject"] for message in observed["sent"]]
    assert subjects == [
        "TradingAgents collection is incomplete",
        "TradingAgents collector is unhealthy",
        "TradingAgents collector is unhealthy",
        "TradingAgents collector recovered",
        "TradingAgents reached its daily X limit",
        "TradingAgents reached its daily X limit",
        "TradingAgents notification test",
    ]
    assert all(message["to"] == "alerts@example.invalid" for message in observed["sent"])
    assert "UNTRUSTED_DETAIL" not in json.dumps(observed["sent"])
    assert observed["receiptKeys"] == [
        "ALERT_RECEIPT_delivery_test",
        "ALERT_RECEIPT_query_slot_coverage_incomplete",
        "ALERT_RECEIPT_runtime_recovered",
        "ALERT_RECEIPT_runtime_unhealthy",
        "ALERT_RECEIPT_x_daily_budget_exhausted",
    ]
