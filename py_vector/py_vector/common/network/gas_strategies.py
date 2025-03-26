from time import time
from typing import Generator

import requests
from brownie import Wei
from brownie.network import gas_price
from brownie.network.gas.bases import SimpleGasStrategy, TimeGasStrategy
from brownie.network.gas.strategies import LinearScalingStrategy

from py_vector.common.network import IS_AVAX_MAINNET, is_test_context


def get_linear_stategy(
    initial_gas=Wei("100 gwei"),
    max_gas=Wei("300 gwei"),
    increment=1.1,
    time_duration=30,
    set_default=None,
):
    linear_stategy = LinearScalingStrategy(
        initial_gas, max_gas, increment, time_duration=time_duration
    )
    if set_default:
        gas_price(linear_stategy)
    return linear_stategy


class SnowtraceStrategy(TimeGasStrategy):
    overshoot_factor = 1.15
    refresh_delay = 15
    last_update = 0
    current_price = 100

    def get_gas_price(self) -> Generator[int, None, None]:
        if time() > self.last_update + self.refresh_delay:
            # soup = BeautifulSoup(requests.get('https://snowtrace.io/gastracker').text, features="lxml")
            try:
                result = requests.get(
                    "http://gavax.blockscan.com/gasapi.ashx?apikey=key&method=gasoracle"
                ).json()
                self.current_price = int(
                    self.overshoot_factor * Wei(f"{result['result']['FastGasPrice']} gwei")
                )
            except:
                self.current_price = self.overshoot_factor * Wei("100 gwei")

            self.last_update = time()
        yield self.current_price


def get_snowtrace_strategy(
    duration=30, overshoot_factor=1.3, set_default=True, ignore_in_tests=True
):
    print("Snowtrace strategy is deprecated at the time")
    return

    if ignore_in_tests and not IS_AVAX_MAINNET:
        return
    strategy = SnowtraceStrategy(duration)
    strategy.overshoot_factor = overshoot_factor
    if set_default:
        gas_price(strategy)
    return strategy
