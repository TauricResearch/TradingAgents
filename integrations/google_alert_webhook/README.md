# Google alert receiver

This Apps Script is the notification boundary for the production collector. It
turns a small allowlist of events into fixed, short emails and never accepts
email text from a request. Release probes are silent.

## One-time setup

1. Create a standalone Google Apps Script project and replace its `Code.gs` and
   manifest with the files in this directory.
2. In **Project Settings → Script properties**, add `ALERT_EMAIL` with one email
   address. Multiple recipients are deliberately rejected.
3. Choose **Deploy → New deployment → Web app**, execute as yourself, and allow
   access to anyone who has the deployment URL. Treat that URL as a secret.
4. Stage the complete URL as `TRADINGAGENTS_ALERT_WEBHOOK_URL` on the Fly app,
   then deploy through `scripts/deploy_collector.sh`.
5. Run the explicit `--test-alert` command from the production runbook once and
   confirm the short test email arrives.

The receiver derives its contract ID from the event table, so there is no second
constant to update by hand. The silent release probe verifies that contract, the configured
recipient, and remaining Apps Script mail quota. Changing the event table without
updating the matching collector contract makes preflight fail instead of silently
drifting. Each event has one durable Script Property containing its 32 most recent
occurrence IDs. An ID in that bounded history is acknowledged without another
email, even when a retry arrives hours later or in a new Apps Script instance.
Fresh `runtime_unhealthy` IDs are also acknowledged and remembered without email
for one hour after the last runtime email, which prevents a Fly restart storm from
flooding the recipient. The collector's normal 24-hour reminder and recovery
events still deliver. Legacy requests without occurrence IDs retain a two-hour
per-event email interval.

The collector persists separate occurrence IDs for a coverage incident, each
daily reminder, and its recovery before sending. An ambiguous or failed attempt
therefore retries the same ID; a genuinely new reminder or incident gets a new
one.

## Updating an existing receiver

Update the receiver before deploying the new collector. In Apps Script, replace
the files, then open **Deploy → Manage deployments**, edit the existing web-app
deployment, select **New version**, and deploy. This preserves the existing URL,
so the Fly secret does not need to change. Creating a separate new deployment
produces a different URL and requires staging that new URL before the collector
deployment.

The receiver temporarily accepts the current strict envelope and the fixed
four-field envelope sent by the previous collector image. Legacy `details` are
ignored, legacy emails use only allowlisted copy, and the old release probe does
not create email. Keep that compatibility path while the old image remains a
rollback target; remove it only after that rollback is intentionally retired.
The next valid alert request for an event also migrates the receiver's original
`{id, sent_at_ms}` receipt in place while retaining that delivered ID, so updating
the existing deployment does not itself repeat an email.

The previous image predates acknowledgement validation. Apps Script cannot set
a non-2xx status on `TextOutput`, so that image cannot distinguish a negative
receiver acknowledgement from successful delivery. Immediately after updating
the existing receiver, run the old image's `--test-alert` command and visually
confirm the email before deploying the new collector. A later rollback can still
deliver valid legacy events, but its negative delivery result is not reliable;
use the Fly health check or an external monitor and restore the current sender
promptly.

Collector releases after this migration need no Google-side work unless the
alert contract changes. Receipt storage stays bounded to one property and 32 IDs
per event. As with any at-least-once notification path, a mail send followed by a
receipt write failure can produce a later duplicate.

This receiver cannot report a total collector, Fly application, or outbound
network outage because those failures prevent the collector from calling it.
Use an independent uptime monitor if notification of that failure mode is
required.
