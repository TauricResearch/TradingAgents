"""The live account (ADR 0010): the demo's executor on OKX's production environment, with
real money, and born paused.

Until it is first unpaused, every hourly run is a shadow run: it syncs the account,
records the orders it would have sent and changes nothing on the exchange (pausing is
described in ``trader.demo.account``). ``python -m trader live resume`` unpauses it,
once UNLOCK_OPEN allows it. Its kill switch is final: once tripped, by its drawdown or
by ``python -m trader live halt``, nothing lifts it, and the experiment is over.

Beyond what pauses the demo account, the live account is paused when the code or the
Signal its orders follow changes (``trader.demo.job.check_fingerprint``) and while its
equity is over MAX_EQUITY; an order whose notional is over MAX_ORDER is refused.
"""

from trader.demo.account import Profile

# Live's absolute limits, in USDT (ADR 0010).
MAX_EQUITY = 2_000.0
MAX_ORDER = 4_000.0

LIVE = Profile(
    "live", production=True, born_paused=True, kill_final=True,
    fingerprinted=True, max_equity=MAX_EQUITY, max_order=MAX_ORDER,
)

# Whether ``live resume`` may unpause the live account: off until #34 opens it, once the
# unlock's conditions in ADR 0010 are met. The tests switch it on to test the command.
UNLOCK_OPEN = False
