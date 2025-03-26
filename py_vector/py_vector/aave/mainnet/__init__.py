import os

from brownie import network

from py_vector.aave.mainnet.contracts_containers import ALL_CONTRACTS
from py_vector.aave.mainnet.deployed_contracts import (DeploymentMap,
                                                       get_deployment)


def test_on_fork_first(main_func, *args, test_network_name="development"):
    test_network_name = os.environ.get("PRERUN_NETWORK_NAME", None) or test_network_name
    current_network = network.show_active()
    network.disconnect()
    network.connect(test_network_name)
    result = main_func()
    for func in args:
        if result is not None:
            func(result)
        else:
            func()

    network.disconnect()
    network.connect(current_network)
