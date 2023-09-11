"""Common utility functions."""

import logging
from typing import Dict, Hashable, List, Sequence, TypeVar


def get_logger():
    """
    Return a logger configured for use by codesurvey modules.
    """
    logger = logging.getLogger('codesurvey')
    logger_handler = logging.StreamHandler()
    logger.addHandler(logger_handler)
    logger_formatter = logging.Formatter('%(asctime)s - %(levelname)s: %(message)s',
                                         '%Y-%m-%d %H:%M:%S')
    logger_handler.setFormatter(logger_formatter)
    logger.setLevel(logging.INFO)
    return logger


logger = get_logger()
"""`logging.Logger` object that codesurvey logs events to during survey runs.

Can be used to customize logging:

```python
import logging
from codesurvey import logger

logger.setLevel(logging.ERROR)
```
"""


class BreakException(Exception):
    """
    Exception used for breaking out of nested loops.
    """


def noop(*args, **kwargs):
    """
    Function that will do nothing when called with any arguments.
    """
    pass


T = TypeVar('T', bound=Hashable)


def get_duplicates(items: Sequence[T]) -> List[T]:
    """
    Returns a list of any duplicate values in items.
    """
    seen = set()
    duplicates = []
    for item in items:
        if item in seen:
            if item not in duplicates:
                duplicates.append(item)
        else:
            seen.add(item)
    return duplicates


def recursive_update(dict_a: Dict, dict_b: Dict):
    """
    Recursively update dict_a by merging nested dictionaries from dict_b.
    """
    for key, b_value in dict_b.items():
        if key not in dict_a:
            dict_a[key] = b_value
        elif isinstance(b_value, dict):
            recursive_update(dict_a[key], b_value)
