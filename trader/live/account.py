"""The live account (ADR 0010): the demo's executor on OKX's production environment, with
real money, and born paused.

Until it is first unpaused, every hourly run is a shadow run: it syncs the account,
records the orders it would have sent and changes nothing on the exchange (pausing is
described in ``trader.demo.account``). ``python -m trader live resume`` unpauses it,
once UNLOCK_OPEN allows it. Its kill switch is final: once tripped, by its drawdown or
by ``python -m trader live halt``, nothing lifts it, and the experiment is over.
"""

from trader.demo.account import Profile

LIVE = Profile("live", production=True, born_paused=True, kill_final=True)

# Whether ``live resume`` may unpause the live account: off until #34 opens it, once the
# unlock's conditions in ADR 0010 are met. The tests switch it on to test the command.
UNLOCK_OPEN = False
