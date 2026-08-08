/* TradingAgents' minimal Google Apps Script notification receiver.
 *
 * Set the ALERT_EMAIL Script Property, deploy this project as a web app, and
 * keep the deployment URL in Fly's TRADINGAGENTS_ALERT_WEBHOOK_URL secret.
 */

const RECEIPT_WINDOW_MS = 2 * 60 * 60 * 1000;
const RUNTIME_UNHEALTHY_THROTTLE_MS = 60 * 60 * 1000;
const RECENT_RECEIPT_LIMIT = 32;
const RECEIPT_PREFIX = "ALERT_RECEIPT_";

// This is the single source for the current collector's accepted events, wire
// kinds, severities, and human-facing copy.
const EVENTS = Object.freeze({
  delivery_test: Object.freeze({
    kind: "test",
    severity: "info",
    subject: "TradingAgents notification test",
    message: "Alert delivery is working. No action is required."
  }),
  query_slot_coverage_incomplete: Object.freeze({
    kind: "incident",
    severity: "warning",
    subject: "TradingAgents collection is incomplete",
    message: "Expected global-news or public-reaction coverage is incomplete. It will be reassessed during a scheduled collection cycle."
  }),
  query_slot_coverage_recovered: Object.freeze({
    kind: "recovery",
    severity: "info",
    subject: "TradingAgents collection recovered",
    message: "Expected evidence coverage is complete again."
  }),
  runtime_unhealthy: Object.freeze({
    kind: "incident",
    severity: "critical",
    subject: "TradingAgents collector is unhealthy",
    message: "The collector stopped completing cycles and is retrying automatically."
  }),
  runtime_recovered: Object.freeze({
    kind: "recovery",
    severity: "info",
    subject: "TradingAgents collector recovered",
    message: "The collector completed a healthy cycle again."
  })
});

// Keep these fixed legacy-only events while the previous collector image is a
// rollback target. Shared legacy events reuse EVENTS and therefore share copy.
const LEGACY_ONLY_EVENTS = Object.freeze({
  singleton_lease_lost: Object.freeze({
    kind: "incident",
    severity: "critical",
    subject: "TradingAgents collector lost its lease",
    message: "Provider work stopped safely after the collector lost its database lease."
  }),
  x_daily_budget_exhausted: Object.freeze({
    kind: "incident",
    severity: "warning",
    subject: "TradingAgents reached its daily X limit",
    message: "No more paid X requests will be made today."
  })
});

function response_(payload) {
  return ContentService.createTextOutput(JSON.stringify(payload))
    .setMimeType(ContentService.MimeType.JSON);
}

function rejected_() {
  return response_({accepted: false});
}

function currentAcknowledgement_(payload, accepted, contractId) {
  const result = {
    schema_version: 1,
    contract_id: contractId,
    kind: payload.kind,
    accepted: accepted
  };
  if (payload.kind === "probe") {
    result.nonce = payload.nonce;
  } else {
    result.idempotency_key = payload.idempotency_key;
  }
  return response_(result);
}

function legacyAcknowledgement_(accepted) {
  return response_({accepted: accepted});
}

function isRecord_(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function hasExactKeys_(value, expected) {
  if (!isRecord_(value)) {
    return false;
  }
  const actual = Object.keys(value).sort();
  const wanted = expected.slice().sort();
  return actual.length === wanted.length && actual.every(function (key, index) {
    return key === wanted[index];
  });
}

function validToken_(value, pattern) {
  return typeof value === "string" && pattern.test(value);
}

function owns_(object, key) {
  return Object.prototype.hasOwnProperty.call(object, key);
}

function contractManifest_() {
  const manifest = {};
  Object.keys(EVENTS).sort().forEach(function (eventName) {
    const spec = EVENTS[eventName];
    manifest[eventName] = [spec.kind, spec.severity];
  });
  return manifest;
}

function contractId_() {
  const digest = Utilities.computeDigest(
    Utilities.DigestAlgorithm.SHA_256,
    JSON.stringify(contractManifest_()),
    Utilities.Charset.UTF_8
  );
  const hex = digest.map(function (byte) {
    const unsigned = byte < 0 ? byte + 256 : byte;
    return ("0" + unsigned.toString(16)).slice(-2);
  }).join("");
  return "alerts_" + hex.slice(0, 24);
}

function recipient_() {
  const raw = PropertiesService.getScriptProperties().getProperty("ALERT_EMAIL");
  if (typeof raw !== "string") {
    return "";
  }
  const recipient = raw.trim();
  const singleEmail = /^[^\s@,;]+@[^\s@,;]+\.[^\s@,;]+$/;
  return recipient.length <= 254 && singleEmail.test(recipient) ? recipient : "";
}

function receiverReady_() {
  const quota = MailApp.getRemainingDailyQuota();
  return recipient_() !== "" &&
    typeof quota === "number" && Number.isFinite(quota) && quota > 0;
}

function readReceipt_(properties, eventName) {
  const encoded = properties.getProperty(RECEIPT_PREFIX + eventName);
  if (!encoded) {
    return null;
  }
  try {
    const receipt = JSON.parse(encoded);
    // Migrate the receiver's original one-ID receipt without forgetting the
    // delivery during rollout. The next accepted request writes the new shape.
    if (
      hasExactKeys_(receipt, ["id", "sent_at_ms"]) &&
      validReceiptId_(receipt.id) &&
      validStoredTime_(receipt.sent_at_ms)
    ) {
      return {
        ids: [receipt.id],
        last_email_ms: receipt.sent_at_ms,
        needs_migration: true
      };
    }
    if (
      !hasExactKeys_(receipt, ["ids", "last_email_ms"]) ||
      !Array.isArray(receipt.ids) ||
      receipt.ids.length > RECENT_RECEIPT_LIMIT ||
      !receipt.ids.every(validReceiptId_) ||
      new Set(receipt.ids).size !== receipt.ids.length ||
      !validStoredTime_(receipt.last_email_ms)
    ) {
      return null;
    }
    return {
      ids: receipt.ids.slice(),
      last_email_ms: receipt.last_email_ms,
      needs_migration: false
    };
  } catch (error) {
    return null;
  }
}

function validReceiptId_(value) {
  return typeof value === "string" && value.length > 0 && value.length <= 64;
}

function validStoredTime_(value) {
  return typeof value === "number" && Number.isFinite(value) && value >= 0;
}

function storedReceipt_(receipt) {
  return JSON.stringify({
    ids: receipt.ids,
    last_email_ms: receipt.last_email_ms
  });
}

function remember_(receipt, receiptId) {
  const ids = receipt.ids.filter(function (candidate) {
    return candidate !== receiptId;
  });
  ids.push(receiptId);
  receipt.ids = ids.slice(-RECENT_RECEIPT_LIMIT);
}

function deliver_(eventName, receiptId, spec, minimumIntervalMs) {
  const lock = LockService.getScriptLock();
  if (!lock.tryLock(5000)) {
    return false;
  }
  try {
    const properties = PropertiesService.getScriptProperties();
    const receipt = readReceipt_(properties, eventName) || {
      ids: [],
      last_email_ms: 0,
      needs_migration: false
    };
    const now = Date.now();
    if (!validReceiptId_(receiptId) || !validStoredTime_(now)) {
      return false;
    }
    if (receipt.ids.indexOf(receiptId) !== -1) {
      if (receipt.needs_migration) {
        properties.setProperty(RECEIPT_PREFIX + eventName, storedReceipt_(receipt));
      }
      return true;
    }

    const age = now - receipt.last_email_ms;
    // A clock correction must not bypass throttling. A future stored send time
    // is safer to suppress than to turn into a duplicate notification.
    if (minimumIntervalMs > 0 && age < minimumIntervalMs) {
      remember_(receipt, receiptId);
      properties.setProperty(RECEIPT_PREFIX + eventName, storedReceipt_(receipt));
      return true;
    }

    const recipient = recipient_();
    const quota = MailApp.getRemainingDailyQuota();
    if (
      !recipient || typeof quota !== "number" ||
      !Number.isFinite(quota) || quota <= 0
    ) {
      return false;
    }
    MailApp.sendEmail(recipient, spec.subject, spec.message);
    remember_(receipt, receiptId);
    receipt.last_email_ms = now;
    properties.setProperty(
      RECEIPT_PREFIX + eventName,
      storedReceipt_(receipt)
    );
    return true;
  } finally {
    lock.releaseLock();
  }
}

function currentProbe_(payload) {
  return hasExactKeys_(payload, ["schema_version", "contract_id", "kind", "nonce"]) &&
    typeof payload.schema_version === "number" &&
    payload.schema_version === 1 &&
    validToken_(payload.contract_id, /^alerts_[0-9a-f]{24}$/) &&
    payload.kind === "probe" &&
    validToken_(payload.nonce, /^[0-9a-f]{32}$/);
}

function currentAlert_(payload) {
  if (!hasExactKeys_(payload, [
    "schema_version",
    "contract_id",
    "kind",
    "idempotency_key",
    "component",
    "event",
    "severity"
  ])) {
    return null;
  }
  if (
    typeof payload.schema_version !== "number" ||
    payload.schema_version !== 1 ||
    !validToken_(payload.contract_id, /^alerts_[0-9a-f]{24}$/) ||
    payload.component !== "collector" ||
    !validToken_(payload.idempotency_key, /^[0-9a-f]{32}$/) ||
    typeof payload.event !== "string" ||
    !owns_(EVENTS, payload.event)
  ) {
    return null;
  }
  const spec = EVENTS[payload.event];
  return payload.kind === spec.kind && payload.severity === spec.severity ? spec : null;
}

function legacySpec_(eventName) {
  if (owns_(EVENTS, eventName)) {
    return EVENTS[eventName];
  }
  return owns_(LEGACY_ONLY_EVENTS, eventName) ? LEGACY_ONLY_EVENTS[eventName] : null;
}

function legacyAlert_(payload) {
  if (!hasExactKeys_(payload, ["component", "event", "severity", "details"])) {
    return null;
  }
  if (
    payload.component !== "collector" ||
    typeof payload.event !== "string" ||
    typeof payload.severity !== "string" ||
    !isRecord_(payload.details)
  ) {
    return null;
  }
  if (payload.event === "release_preflight_probe") {
    return payload.severity === "info" ? {probe: true} : null;
  }
  const spec = legacySpec_(payload.event);
  return spec && payload.severity === spec.severity ? {probe: false, spec: spec} : null;
}

function doPost(event) {
  try {
    const body = event && event.postData && event.postData.contents;
    if (typeof body !== "string" || body.length > 4096) {
      return rejected_();
    }
    const payload = JSON.parse(body);
    const contractId = contractId_();

    if (currentProbe_(payload)) {
      const accepted = payload.contract_id === contractId && receiverReady_();
      return currentAcknowledgement_(payload, accepted, contractId);
    }

    const currentSpec = currentAlert_(payload);
    if (currentSpec) {
      const minimumIntervalMs = payload.event === "runtime_unhealthy" ?
        RUNTIME_UNHEALTHY_THROTTLE_MS : 0;
      const accepted = payload.contract_id === contractId && deliver_(
          payload.event,
          payload.idempotency_key,
          currentSpec,
          minimumIntervalMs
        );
      return currentAcknowledgement_(payload, accepted, contractId);
    }

    const legacy = legacyAlert_(payload);
    if (legacy) {
      if (legacy.probe) {
        return legacyAcknowledgement_(receiverReady_());
      }
      const legacyReceiptId = "legacy-v1:" + payload.event + ":" +
        Date.now().toString(36);
      return legacyAcknowledgement_(
        deliver_(
          payload.event,
          legacyReceiptId,
          legacy.spec,
          RECEIPT_WINDOW_MS
        )
      );
    }
    return rejected_();
  } catch (error) {
    return rejected_();
  }
}
