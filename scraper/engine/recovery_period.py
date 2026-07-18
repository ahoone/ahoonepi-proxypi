import numpy as np

from scraper.Config import Config


def recovery_period() -> int:
    """
    return waiting time in milliseconds
    """
    # return max(
    #     Config.RECOVERY_PERIOD_MINIMUM,
    #     np.random.normal(
    #         loc=Config.RECOVERY_PERIOD_MEAN, scale=Config.RECOVERY_PERIOD_SPREAD
    #     ),
    # )
    return Config.RECOVERY_PERIOD_MINIMUM
