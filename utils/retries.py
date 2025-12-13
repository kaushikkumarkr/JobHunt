import time
import functools
import logging
import random
from typing import Type, Tuple, Union

logger = logging.getLogger(__name__)

def retry_with_backoff(
    retries: int = 3,
    backoff_in_seconds: int = 1,
    exceptions: Union[Type[Exception], Tuple[Type[Exception], ...]] = (Exception,)
):
    """
    Decorator for exponential backoff retries.
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            x = 0
            while True:
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    if x == retries:
                        logger.error(f"Function {func.__name__} failed after {retries} retries. Error: {e}")
                        raise
                    
                    sleep = (backoff_in_seconds * 2 ** x) + random.uniform(0, 1)
                    logger.warning(f"Error in {func.__name__}: {e}. Retrying in {sleep:.2f}s...")
                    time.sleep(sleep)
                    x += 1
        return wrapper
    return decorator
