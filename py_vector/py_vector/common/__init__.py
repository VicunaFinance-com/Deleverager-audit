from brownie import Wei

from .network.gas_strategies import get_snowtrace_strategy

ETHER = Wei("1 ether")
HOUR = 3600
DAY = 24 * HOUR
YEAR = 365 * DAY
UINT_MAX = 2**256 - 1
