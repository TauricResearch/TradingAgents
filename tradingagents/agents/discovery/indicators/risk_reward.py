import logging

logger = logging.getLogger(__name__)


def calculate_stop_loss(price: float, atr: float, multiplier: float = 1.5) -> float:
    return price - (atr * multiplier)


def calculate_reward_target(price: float, resistance: float) -> float:
    return resistance


def calculate_risk_reward_ratio(price: float, stop: float, target: float) -> float:
    risk = price - stop
    if risk == 0:
        return 0.0

    reward = target - price
    return reward / risk


def calculate_risk_reward_score(rr_ratio: float) -> float:
    if rr_ratio < 0:
        return 0.0

    if rr_ratio >= 3.0:
        return 0.9 + min((rr_ratio - 3.0) / 10, 0.1)
    elif rr_ratio >= 2.0:
        return 0.7 + (rr_ratio - 2.0) / 5
    elif rr_ratio >= 1.0:
        return 0.4 + (rr_ratio - 1.0) * 0.3
    else:
        return rr_ratio * 0.4
