from enum import Enum

import pytest
from brownie import (ZERO_ADDRESS, BalancerPoolExit, BeetsReentrancy,
                     BeetsVaultOracle, CentralOracle, Wei, accounts, interface)


class OracleType(int, Enum):
    API3 = 0
    CHAINLINK = 1
    PYTH = 2
    PEGGEDORACLE = 3


# @pytest.fixture(autouse=True)
# def isolation(fn_isolation):
#     pass


def test_beets_reentrancy():

    WS = interface.IERC20("0x039e2fB66102314Ce7b64Ce5Ce3E5183bc94aD38")
    STS = interface.IERC20("0xE5DA20F15420aD15DE0fa650600aFc998bbE3955")
    whale = "0x10891D6735b76b5435db8E446ecDA3B640322038"
    deployer = accounts[0]
    deployer_params = {"from": deployer}
    TEST_POOL = "0x374641076B68371e69D03C417DAc3E5F236c32FA"
    CENTRAL_ORACLE = "0x13773dc9fB30bF4B2a044101f4eec45aDf85599b"
    BEEFY_VAULT = "0x02D742f182D2a588c54E7DC998aD19f9D795bC51"
    amount = 10e18

    # central_oracle = cen
    oracle = BeetsVaultOracle.deploy(BEEFY_VAULT, CENTRAL_ORACLE, deployer_params)
    reentrant_contract = BeetsReentrancy.deploy(oracle, deployer_params)
    STS.transfer(reentrant_contract, amount, {"from": accounts.at(whale, force=True)})
    reentrant_contract.attack(TEST_POOL, STS, amount, 0, deployer_params)
