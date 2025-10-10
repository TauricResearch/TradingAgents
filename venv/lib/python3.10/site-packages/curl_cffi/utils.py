import warnings


class CurlCffiWarning(UserWarning, RuntimeWarning):
    pass


def config_warnings(on: bool = False):
    if on:
        warnings.simplefilter("default", category=CurlCffiWarning)
    else:
        warnings.simplefilter("ignore", category=CurlCffiWarning)


def is_pro():
    return False
