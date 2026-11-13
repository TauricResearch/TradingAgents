"""The live account (ADR 0010): the demo's executor on OKX's production environment, with
real money, and born paused.

Until it is first unpaused, every hourly run is a shadow run: it syncs the account,
records the orders it would have sent and changes nothing on the exchange (pausing is
described in ``trader.demo.account``). ``python -m trader live resume`` unpauses it,
once UNLOCK_OPEN allows it. Its kill switch is final: once tripped, by its drawdown or
by ``python -m trader live halt``, nothing lifts it, and the experiment is over.

Beyond what pauses the demo account, the live account is paused when the code or the
Signal its orders follow changes (``trader.demo.job.check_fingerprint``) and while its
equity is over MAX_EQUITY; an order that would leave a position of more notional than
MAX_POSITION is refused, one that only reduces a position never is.
"""

from trader.demo.account import Profile

# Live's absolute limits, in USDT (ADR 0010).
MAX_EQUITY = 2_000.0
MAX_POSITION = 4_000.0  # notional of a contract's position after an order

LIVE = Profile(
    "live", production=True, born_paused=True, kill_final=True,
    fingerprinted=True, max_equity=MAX_EQUITY, max_position=MAX_POSITION,
)

# Whether ``live resume`` may unpause the live account. Open since #34, the last of the code
# the unlock waits for (ADR 0010); the user's conditions are a person's to check, but for the
# dashboard's token, which ``live resume`` checks. False closes the unlock again.
UNLOCK_OPEN = True
