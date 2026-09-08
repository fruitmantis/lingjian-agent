"""Bounded execution limits. Test overrides may shorten, never extend, limits."""
import os


def seconds(name, maximum):
    try:
        value = float(os.getenv(name, str(maximum)))
        return value if 0 < value <= maximum else float(maximum)
    except ValueError:
        return float(maximum)


def model_timeout():
    return seconds('DEVELOPMENT_MODEL_TIMEOUT_SECONDS', 180)


def run_timeout():
    return seconds('DEVELOPMENT_RUN_TIMEOUT_SECONDS', 600)
