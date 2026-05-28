import numpy as np

from Config import Config


def erholungszeit() -> int:
    """
    return waiting time in milliseconds
    """
    return max(
        Config.ERHOLUNGSZEIT_MINIMUM,
        np.random.normal(
            loc=Config.ERHOLUNGSZEIT_MEAN, scale=Config.ERHOLUNGSZEIT_SPREAD
        ),
    )
