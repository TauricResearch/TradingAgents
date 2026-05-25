"""Hash-chained append-only trace ledger (T1.3).

Wraps the JSONL file produced by :class:`tradingagents.audit.trace_callback.TraceCallback`
in a cryptographic chain so a third party can detect post-hoc tampering
without trusting our process.

Mechanism, in one paragraph
---------------------------
Each appended record carries a ``prev_hash`` field equal to the SHA-256
of the **previous** record's on-disk line (the canonical JSON,
including its own prev_hash). The very first record uses ``GENESIS_HASH``
as its prev_hash. To verify, walk the file front-to-back, hashing each
line and confirming the next line's ``prev_hash`` matches. Any
modification to a record at line N invalidates the chain from N+1
onward, which is exactly the property auditors need: "show me your
decision log for Q1" plus "here's the verifier" lets them check the
file hasn't been edited since whenever the last record was written.

What this gives you / doesn't
-----------------------------
- DOES detect: edit, delete, reorder, or insert lines after the fact.
- DOES NOT prevent: the process itself writing a fresh chain (if you
  control the writer, you can produce any chain you like). For that
  threat model, anchor the daily root hash to an external service
  like OpenTimestamps (T3.6) — that's a separate work item.
- DOES NOT prevent: deletion of the entire ledger file. We address
  that via offsite backups and operating procedures, not crypto.

Schema compatibility
--------------------
Records written in T1.2 (before this PR) have ``prev_hash=""``. They
are NOT in a chain. ``verify`` treats them as "unchained / pre-T1.3
format" and reports every line from #2 onward as broken — which is
honest, the chain genuinely doesn't exist. Re-run with T1.3 enabled
to produce a chained ledger going forward.
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import List, Literal, Optional, Union

from tradingagents.audit.schemas import TraceRecord, canonical_json

logger = logging.getLogger(__name__)

# Genesis marker for the first record. We use a constant 64-hex string
# (the SHA-256 of nothing-came-before) so a verifier can distinguish:
#   - "this is the start of a valid T1.3 chain"   (prev_hash = GENESIS_HASH)
#   - "this is a T1.2 record without a chain"     (prev_hash = "")
GENESIS_HASH = "0" * 64


@dataclass
class VerifyResult:
    """Outcome of verifying a ledger file.

    ``ok`` is True iff every record in the file has a prev_hash that
    matches the previous record's computed hash, AND the file isn't in
    the pre-T1.3 unchained format. ``broken_lines`` is 1-indexed.
    ``format`` distinguishes a corrupt chain from a file that was
    written before T1.3 existed.
    """
    ok: bool
    total_records: int
    broken_lines: List[int]
    format: Literal["chained", "unchained_pre_t1_3", "empty", "corrupt"]


def _hash_line(line: str) -> str:
    """SHA-256 hex digest of a line as stored on disk (newline stripped)."""
    return hashlib.sha256(line.rstrip("\n").encode("utf-8")).hexdigest()


class HashChainLedger:
    """Append-only JSONL with a SHA-256 chain linking consecutive records.

    Construct one per trace file. When the file already exists, the
    ledger resumes by reading the last record's hash and continuing the
    chain. When it doesn't exist, the first append uses GENESIS_HASH as
    its prev_hash.

    Thread-safe: an internal lock guards file writes and the cached
    last-hash. Callers may invoke ``append`` concurrently; ledger
    serialises them.
    """

    def __init__(self, path: Union[str, Path]) -> None:
        self.path = Path(path).expanduser()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._last_hash: str = self._read_last_hash()

    # ------------------------------------------------------------------ #
    # Resume / state
    # ------------------------------------------------------------------ #

    def _read_last_hash(self) -> str:
        """Read the existing file's last record and return its on-disk hash.

        If the file is missing or empty, return ``GENESIS_HASH`` so the
        next append starts a fresh chain.

        If the last line fails to parse as JSON, we still return its
        raw hash — the chain is over what was committed, regardless of
        whether the content is well-formed. A verifier will catch any
        downstream issue.
        """
        if not self.path.exists():
            return GENESIS_HASH
        try:
            # Read last non-empty line — small files this is fine; for
            # large ones we could seek backward, but trace files are
            # bounded by a single propagate() call (~MB, not GB).
            lines = self.path.read_text(encoding="utf-8").splitlines()
        except Exception as e:
            logger.warning(
                "ledger %s: failed to read existing file (%s); "
                "starting chain from GENESIS_HASH",
                self.path, e,
            )
            return GENESIS_HASH
        last = ""
        for line in reversed(lines):
            if line.strip():
                last = line
                break
        if not last:
            return GENESIS_HASH
        return _hash_line(last)

    # ------------------------------------------------------------------ #
    # Append
    # ------------------------------------------------------------------ #

    def append(self, record: TraceRecord) -> str:
        """Set ``record.prev_hash`` from chain state, persist, return hash.

        Mutates ``record`` in place so the in-memory copy held by
        TraceCallback reflects the same prev_hash that's on disk.
        """
        with self._lock:
            record.prev_hash = self._last_hash
            line = record.canonical()  # canonical JSON INCLUDING prev_hash
            try:
                with open(self.path, "a", encoding="utf-8") as f:
                    f.write(line + "\n")
            except Exception as e:
                # Audit subsystem failure must never break the user's
                # run. We log and re-raise — TraceCallback catches and
                # converts to a warning. The chain state is left at
                # _last_hash (unchanged), so the next successful append
                # carries on.
                logger.warning("ledger %s: append failed: %s", self.path, e)
                raise
            new_hash = _hash_line(line)
            self._last_hash = new_hash
            return new_hash

    # ------------------------------------------------------------------ #
    # Verify
    # ------------------------------------------------------------------ #

    def verify(self) -> VerifyResult:
        """Verify this ledger's chain. See ``verify_ledger`` for details."""
        return verify_ledger(self.path)


def verify_ledger(path: Union[str, Path]) -> VerifyResult:
    """Walk a ledger file and check the SHA-256 chain.

    Returns a :class:`VerifyResult`. ``format`` reports:

    - ``"empty"``: file missing or contains no records
    - ``"unchained_pre_t1_3"``: every record has ``prev_hash == ""``,
      meaning the file predates T1.3. Not broken — just not chained.
    - ``"chained"``: T1.3+ format. ``ok`` is True iff every prev_hash
      matches and no record fails to parse.
    - ``"corrupt"``: file is in chained format but the chain is broken
      somewhere. ``broken_lines`` lists 1-indexed positions.

    A record at line N appearing "broken" can mean N itself was edited,
    OR N-1 was edited and N now disagrees with N-1's recomputed hash.
    By convention we report N — the first downstream record affected.
    """
    path = Path(path).expanduser()
    if not path.exists():
        return VerifyResult(ok=True, total_records=0, broken_lines=[], format="empty")

    lines = path.read_text(encoding="utf-8").splitlines()
    nonempty: List[tuple] = []  # (1-indexed line_no, raw_line)
    for i, line in enumerate(lines, start=1):
        if line.strip():
            nonempty.append((i, line))

    if not nonempty:
        return VerifyResult(ok=True, total_records=0, broken_lines=[], format="empty")

    # Detect the pre-T1.3 format: ALL records have prev_hash == "".
    # We need to peek inside to make this call; a stray "" on a single
    # record after a chain isn't this case (and would be reported as
    # broken in the chained branch).
    try:
        parsed = [json.loads(line) for _, line in nonempty]
    except json.JSONDecodeError:
        # File has unparseable JSON, fall through to chained verify
        # which will flag the specific broken lines.
        parsed = []

    if parsed and all(p.get("prev_hash", "") == "" for p in parsed):
        return VerifyResult(
            ok=False,  # not strictly "broken" but not chained-verifiable
            total_records=len(nonempty),
            broken_lines=[],
            format="unchained_pre_t1_3",
        )

    # Chained verify. Audit semantics: once the chain breaks at line N,
    # every line from N onward is unverified — the file is no longer
    # cryptographically anchored to the original chain past that point.
    # This is more pessimistic than "report only the immediate
    # mismatch" but it's the right framing for an auditor: "we can vouch
    # for lines 1..N-1 and only those". Once broken, ``chain_broken``
    # stays True for the rest of the walk so every downstream line
    # joins ``broken_lines`` regardless of its individual prev_hash.
    broken: List[int] = []
    expected_prev = GENESIS_HASH
    chain_broken = False
    for line_no, line in nonempty:
        if chain_broken:
            broken.append(line_no)
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            broken.append(line_no)
            chain_broken = True
            continue
        if rec.get("prev_hash") != expected_prev:
            broken.append(line_no)
            chain_broken = True
            continue
        expected_prev = _hash_line(line)

    return VerifyResult(
        ok=not broken,
        total_records=len(nonempty),
        broken_lines=broken,
        format="chained" if not broken else "corrupt",
    )
