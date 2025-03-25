from enum import Enum

import pytest
from brownie import (ZERO_ADDRESS, BalancerPoolExit, BeetsVaultOracle,
                     CentralOracle, Wei, accounts, interface)


class OracleType(int, Enum):
    API3 = 0
    CHAINLINK = 1
    PYTH = 2
    PEGGEDORACLE = 3


# @pytest.fixture(autouse=True)
# def isolation(fn_isolation):
#     pass


def test_beets_amounts():

    user = accounts[0]
    user_params = {"from": user}

    BEETS_VAULT = "0xBA12222222228d8Ba445958a75a0704d566BF2C8"
    exit_helper = BalancerPoolExit.deploy(BEETS_VAULT, user_params)

    beets_lp_token = interface.IERC20("0x374641076B68371e69D03C417DAc3E5F236c32FA")
    beets_lp_holder = "0xf92961602Ac82eF66bdc590C16E25855018f1379"
    LP_AMOUNT = 1e18
    assert beets_lp_token.balanceOf(beets_lp_holder) > LP_AMOUNT

    beets_lp_token.transfer(exit_helper, LP_AMOUNT, {"from": beets_lp_holder})

    vault = interface.IBeefyVault(
        "0x02D742f182D2a588c54E7DC998aD19f9D795bC51"
    )  # Beefy vault address

    lp_token = interface.IBeetsPool(vault.want())
    pool_id = lp_token.getPoolId()
    token0 = interface.IERC20("0x039e2fB66102314Ce7b64Ce5Ce3E5183bc94aD38")  # First token in LP
    token1 = interface.IERC20("0xE5DA20F15420aD15DE0fa650600aFc998bbE3955")  # Second token in LP
    assert token0.balanceOf(exit_helper) == 0
    assert token1.balanceOf(exit_helper) == 0  # helper does not have any tokens

    api3_oracle0 = "0xEFBA61Ad1B7F785eeAb3EA3B5A717d19Ba8344bb"  # API3 oracle for token0
    pegged_oracle1 = "0x86235363749D25Ac686f64184F9f0d7188A05573"  # Chainlink oracle for token1

    # Deploy and configure central oracle
    central_oracle = CentralOracle.deploy(user_params)

    # Add tokens to central oracle
    # token0 with API3 oracle
    central_oracle.addToken(
        token0,
        api3_oracle0,
        bytes("0x", "utf-8"),  # No Pyth ID needed
        OracleType.API3,
        user_params,
    )

    # token1 with Chainlink oracle
    central_oracle.addToken(
        token1,
        pegged_oracle1,
        bytes("0x", "utf-8"),  # No Pyth ID needed
        OracleType.PEGGEDORACLE,
        user_params,
    )

    # Deploy vault oracle
    vault_oracle = BeetsVaultOracle.deploy(vault, central_oracle, user_params)
    price = vault_oracle.getBPTPrice()
    tx = exit_helper.exitBalancerPool(pool_id, LP_AMOUNT, exit_helper, user_params)
    balance_token_0 = token0.balanceOf(exit_helper)
    balance_token_1 = token1.balanceOf(exit_helper)
    value_token_0 = balance_token_0 * central_oracle.getAssetPrice(token0)
    value_token_1 = balance_token_1 * central_oracle.getAssetPrice(token1)
    assert (value_token_0 + value_token_1) // LP_AMOUNT == price


def test_beefy_amounts():

    user = accounts[0]
    user_params = {"from": user}

    BEETS_VAULT = "0xBA12222222228d8Ba445958a75a0704d566BF2C8"
    exit_helper = BalancerPoolExit.deploy(BEETS_VAULT, user_params)

    vault = interface.IBeefyVault(
        "0x02D742f182D2a588c54E7DC998aD19f9D795bC51"
    )  # Beefy vault address

    lp_token = interface.IBeetsPool(vault.want())

    vault_holder = accounts.at("0xB0bcfFe2D1C8f8cE141E3b4dd3edfFB705aF7d55", force=True)

    pool_id = lp_token.getPoolId()
    token0 = interface.IERC20("0x039e2fB66102314Ce7b64Ce5Ce3E5183bc94aD38")  # First token in LP
    token1 = interface.IERC20("0xE5DA20F15420aD15DE0fa650600aFc998bbE3955")  # Second token in LP
    assert token0.balanceOf(exit_helper) == 0
    assert token1.balanceOf(exit_helper) == 0  # helper does not have any tokens

    api3_oracle0 = "0xEFBA61Ad1B7F785eeAb3EA3B5A717d19Ba8344bb"  # API3 oracle for token0
    pegged_oracle1 = "0x86235363749D25Ac686f64184F9f0d7188A05573"  # Chainlink oracle for token1

    # Deploy and configure central oracle
    central_oracle = CentralOracle.deploy(user_params)

    # Add tokens to central oracle
    # token0 with API3 oracle
    central_oracle.addToken(
        token0,
        api3_oracle0,
        bytes("0x", "utf-8"),  # No Pyth ID needed
        OracleType.API3,
        user_params,
    )

    # token1 with Chainlink oracle
    central_oracle.addToken(
        token1,
        pegged_oracle1,
        bytes("0x", "utf-8"),  # No Pyth ID needed
        OracleType.PEGGEDORACLE,
        user_params,
    )

    # Deploy vault oracle
    vault_oracle = BeetsVaultOracle.deploy(vault, central_oracle, user_params)

    vault_amount = 5e18

    vault.transfer(user, vault_amount, {"from": vault_holder})

    amounts, _ = vault_oracle.getTokenAmountsForShare(vault_amount)

    expected_shares = int(int(int(vault_amount) * int(vault.getPricePerFullShare())) // 1e18)
    before_withdraw = lp_token.balanceOf(user)
    vault.withdrawAll({"from": user})
    after_withdraw = lp_token.balanceOf(user)

    assert abs(after_withdraw - before_withdraw - int(expected_shares)) <= Wei("0.00001 ether")

    lp_token.transfer(exit_helper, after_withdraw, {"from": user})

    tx = exit_helper.exitBalancerPool(
        pool_id, after_withdraw - before_withdraw, exit_helper, user_params
    )
    balance_token_0 = token0.balanceOf(exit_helper)
    balance_token_1 = token1.balanceOf(exit_helper)
    assert (
        abs(amounts[0] - balance_token_0)
        < 0.0001 * 10 ** interface.IERC20Metadata(token0).decimals()
    )
    assert (
        abs(amounts[1] - balance_token_1)
        < 0.0001 * 10 ** interface.IERC20Metadata(token1).decimals()
    )


def test_beefy_vault_oracle():

    user = accounts.load("vicuna", "vicuna")
    user_params = {"from": user}

    # Example addresses (these should be replaced with actual addresses)
    vault = interface.IBeefyVault(
        "0x02D742f182D2a588c54E7DC998aD19f9D795bC51"
    )  # Beefy vault address

    lp_token = interface.IBeetsPool(vault.want())
    pool_id = lp_token.getPoolId()
    beets_vault = interface.IBeetsVaultV2(lp_token.getVault())
    raw_tokens, raw_balances, _ = beets_vault.getPoolTokens(pool_id)

    token0 = "0x039e2fB66102314Ce7b64Ce5Ce3E5183bc94aD38"  # First token in LP
    token1 = "0xE5DA20F15420aD15DE0fa650600aFc998bbE3955"  # Second token in LP
    assert raw_tokens[0] == token0
    assert raw_tokens[-1] == token1
    api3_oracle0 = "0xEFBA61Ad1B7F785eeAb3EA3B5A717d19Ba8344bb"  # API3 oracle for token0
    pegged_oracle1 = "0x86235363749D25Ac686f64184F9f0d7188A05573"  # Chainlink oracle for token1

    # Deploy and configure central oracle
    central_oracle = CentralOracle.deploy(user_params)

    # Add tokens to central oracle
    # token0 with API3 oracle
    central_oracle.addToken(
        token0,
        api3_oracle0,
        bytes("0x", "utf-8"),  # No Pyth ID needed
        OracleType.API3,
        user_params,
    )

    # token1 with Chainlink oracle
    central_oracle.addToken(
        token1,
        pegged_oracle1,
        bytes("0x", "utf-8"),  # No Pyth ID needed
        OracleType.PEGGEDORACLE,
        user_params,
    )

    # Deploy vault oracle
    vault_oracle = BeetsVaultOracle.deploy(vault, central_oracle, user_params)

    share_amount = 1e18  # 1 vault share
    expected_lp = int(int(vault.getPricePerFullShare() * share_amount) // 1e18)
    lp_equiv_of_one_share = vault_oracle.sharesToLp(share_amount)
    assert abs((lp_equiv_of_one_share - expected_lp)) < Wei(
        "0.0000000001 ether"
    ), "sharesToLp calculation incorrect"

    # Test getTokenAmounts
    lp_supply = lp_token.getActualSupply()
    expected_BPT0, expected_BPT1 = raw_balances[0], raw_balances[-1]

    amounts, _ = vault_oracle.getTotalTokensInPool()
    # Check amounts match tokens
    assert amounts[0] == expected_BPT0, "token0 amount incorrect"
    assert amounts[1] == expected_BPT1, "token1 amount incorrect"

    # Test central oracle price queries
    # API3 oracle for token0
    api3_price0 = interface.AggregatorInterface(api3_oracle0).latestAnswer()
    api3_decimals = interface.AggregatorInterface(api3_oracle0).decimals()
    expected_price0 = api3_price0
    if api3_decimals < 8:
        expected_price0 = expected_price0 * (10 ** (8 - api3_decimals))
    elif api3_decimals > 8:
        expected_price0 = expected_price0 / (10 ** (api3_decimals - 8))

    # Chainlink oracle for token1
    chainlink_price1 = interface.AggregatorInterface(pegged_oracle1).latestAnswer()
    chainlink_decimals = interface.AggregatorInterface(pegged_oracle1).decimals()
    expected_price1 = chainlink_price1
    if chainlink_decimals < 8:
        expected_price1 = expected_price1 * (10 ** (8 - chainlink_decimals))
    elif chainlink_decimals > 8:
        expected_price1 = expected_price1 / (10 ** (chainlink_decimals - 8))

    # Test central oracle prices
    actual_price0 = central_oracle.getAssetPrice(token0)
    actual_price1 = central_oracle.getAssetPrice(token1)
    assert actual_price0 == expected_price0, "central oracle token0 price incorrect"
    assert actual_price1 == expected_price1, "central oracle token1 price incorrect"

    # Test vault oracle token prices (should match central oracle)
    actual_price0 = vault_oracle.getTokenPrice(token0)
    actual_price1 = vault_oracle.getTokenPrice(token1)
    assert actual_price0 == expected_price0, "vault oracle token0 price incorrect"
    assert actual_price1 == expected_price1, "vault oracle token1 price incorrect"

    # Test total value calculation
    token0_decimals = interface.IERC20Metadata(token0).decimals()
    token1_decimals = interface.IERC20Metadata(token1).decimals()

    amounts_vault, tokens = vault_oracle.getTotalTokensInPool()
    # Convert amounts to 18 decimals
    amount0_18 = amounts_vault[0] * (10 ** (18 - token0_decimals))
    amount1_18 = amounts_vault[1] * (10 ** (18 - token1_decimals))

    # Calculate expected total value
    expected_total = int(
        (int(int(amount0_18 * expected_price0) + int(amount1_18 * expected_price1)) // 1e18)
    )
    # supply = beets_vault.totalSupply()

    # assert (
    #     abs((actual_total - expected_total)) < 0.0001 * 10**8
    # ), "total value calculation incorrect"
    #
    expected_price = lp_equiv_of_one_share * expected_total / lp_supply

    share_amounts, _ = vault_oracle.getTokenAmountsForShare(share_amount)
    assert share_amounts[0] == lp_equiv_of_one_share * amounts_vault[0] // lp_supply
    assert share_amounts[1] == lp_equiv_of_one_share * amounts_vault[1] // lp_supply

    # Test final vault share price
    share_price = vault_oracle.latestAnswer()
    assert share_price > 0, "share price should be positive"
    assert abs(share_price - int(expected_price)) <= 1, "share price calculation incorrect"
    # Test sharesToLp
