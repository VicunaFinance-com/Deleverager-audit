from functools import wraps

import pytest
from brownie import chain, history
from brownie.exceptions import EventLookupError


def debug_decorator(traceback=False, snapshot=True, full_trace=False, events=False):
    def called_func(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if snapshot:
                chain.snapshot()
            try:
                func(*args, **kwargs)
            except Exception as e:
                try:
                    if events:
                        if isinstance(events, list):
                            history_events = history[-1].events
                            for topic in events:
                                print(f"{topic}:{history_events[topic]}")
                        else:
                            print(history[-1].events)
                except EventLookupError as e:
                    pass
                    # TODO: catch event did not fire
                tx = history[-1]
                if full_trace is not None:
                    print(tx.call_trace(full_trace))
                if traceback:
                    print(tx.traceback())
                raise
            finally:
                if snapshot:
                    chain.revert()

        return wrapper

    return called_func


@pytest.fixture
def simple_isolation():
    # initial_height = chain.height
    chain.snapshot()
    yield
    chain.revert()
    # diff = chain.height - initial_height
    # if diff: chain.undo(diff)
