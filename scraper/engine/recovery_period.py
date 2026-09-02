import numpy as np

from scraper.config import config


def recovery_period() -> int:
    """
    return waiting time in milliseconds
    """
    # return max(
    #     config.RECOVERY_PERIOD_MINIMUM,
    #     np.random.normal(
    #         loc=config.RECOVERY_PERIOD_MEAN, scale=config.RECOVERY_PERIOD_SPREAD
    #     ),
    # )
    return config.RECOVERY_PERIOD_MINIMUM
