import os
from contextlib import contextmanager

from brownie import chain, history, network

IS_AVAX_MAINNET = network.is_connected() and "avax" in (network.show_active() or "")
# IS_METIS_MAINNET = network.is_connected() and 'metis-main' in (network.show_active() or '')
IS_MAINNET = network.is_connected() and "metis" in (network.show_active() or "")
IS_BNB_MAINNET = network.is_connected() and "bnb" in (network.show_active() or "")
IS_ARBITRUM_MAINNET = network.is_connected() and "arbitrum" in (
    network.show_active() or ""
)
IS_MANTLE_MAINNET = network.is_connected() and "mantle" in (network.show_active() or "")
IS_MAINNET = (
    IS_ARBITRUM_MAINNET
    or IS_BNB_MAINNET
    or IS_MAINNET
    or IS_AVAX_MAINNET
    or IS_MANTLE_MAINNET
)


def is_test_context():
    return "PYTEST_CURRENYT_TEST" in os.environ


@contextmanager
def store_transactions_in(save_list):
    first_block = len(chain)
    yield
    while True:
        tx = history[-len(save_list) - 1]
        if tx.block_number >= first_block:
            save_list.append(tx)
        else:
            break


class ChainCheckpoint:
    checkpoint_block: int = None

    def __init__(self):
        self.checkpoint_block = len(chain)

    def all_tx_since(self, start_block=None):
        start_block = len(chain) or start_block
        txs = []
        cursor = -1
        while history[cursor].block_number > start_block:
            cursor -= 1
        while True:
            tx = history[cursor]
            if tx.block_number >= self.checkpoint_block:
                txs.append(tx)
            else:
                return txs
            cursor -= 1

    def revert_to(self):
        while len(chain) > self.checkpoint_block:
            chain.undo(len(chain) - self.checkpoint_block)

    def count_event_triggers_since(self, event_name: str, start_block=None):
        txs = self.all_tx_since(start_block=start_block)
        return count_event_triggers(txs, event_name)


def count_event_triggers(transactions_list, event_name):
    return sum(tx.events.count(event_name) for tx in transactions_list)
