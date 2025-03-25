from brownie import CentralOracle, SwapXBeefyVaultOracle, accounts, interface, reverts, Wei

# add test where central oracle is not set


def test_beefy_vault_oracle():
    user = accounts.load("vicuna", "vicuna")
    user_params = {"from": user}

    # Example addresses (these should be replaced with actual addresses)
    vault = interface.IBeefyVault("0xd50190C922f252dA3A8106f527F41dFFe1B16067")  # Beefy vault address
    lp_token = interface.IICHIVault(vault.want())  # ICHIVault address
    token0 = "0x039e2fB66102314Ce7b64Ce5Ce3E5183bc94aD38"  # First token in LP
    token1 = "0xE5DA20F15420aD15DE0fa650600aFc998bbE3955"  # Second token in LP
    api3_oracle0 = "0xEFBA61Ad1B7F785eeAb3EA3B5A717d19Ba8344bb"  # API3 oracle for token0
    pegged_oracle1 = "0x86235363749D25Ac686f64184F9f0d7188A05573"  # Pegged oracle for token1

    assert token0 == lp_token.token0(), "token0 address incorrect"
    assert token1 == lp_token.token1(), "token1 address incorrect"

    # Deploy and configure central oracle
    central_oracle = CentralOracle.deploy(user_params)

    #  test reverting when the central oracle is not set
    # try:
    #     SwapXBeefyVaultOracle.deploy(
    #         vault,
    #         lp_token,
    #         central_oracle.address,
    #         user_params
    #     )
    #     assert False, "SHould have reverted"
    # except:
    #     pass
    
    # Add tokens to central oracle
    # token0 with API3 oracle
    central_oracle.addToken(
        token0,
        api3_oracle0,
        bytes("0x", "utf-8"),  # No Pyth ID needed
        0,  # API3 type = 0
        user_params
    )
    # try:
    #     SwapXBeefyVaultOracle.deploy(
    #         vault,
    #         lp_token,
    #         central_oracle.address,
    #         user_params
    #     )
    #     assert False, "SHould have reverted"
    # except:
    #     pass
    
    # token1 with Chainlink oracle
    central_oracle.addToken(
        token1,
        pegged_oracle1,
        bytes("0x", "utf-8"),  # No Pyth ID needed
        3,  # Pegged type = 3
        user_params
    )

    # Deploy vault oracle
    vault_oracle = SwapXBeefyVaultOracle.deploy(
        vault,
        central_oracle.address,
        user_params
    )

    # Test sharesToLp
    share_amount = 1e18  # 1 vault share
    expected_lp = int(int(vault.getPricePerFullShare() * share_amount) // 1e18)
    actual_lp = vault_oracle.sharesToLp(share_amount)
    assert abs((actual_lp - expected_lp)) < Wei("0.0000000001 ether"), "sharesToLp calculation incorrect"

    # Test getTokenAmounts
    lp_contract = interface.IICHIVault(lp_token)
    lp_amount = actual_lp  # 1 LP token
    total0, total1 = lp_contract.getTotalAmounts()
    lp_supply = lp_contract.totalSupply()
    
    expected0 = total0 * lp_amount / lp_supply
    expected1 = total1 * lp_amount / lp_supply
    
    amounts, tokens = vault_oracle.getTokenAmounts(lp_amount)
    # Check amounts match tokens
    assert tokens[0] == lp_contract.token0(), "token0 address incorrect"
    assert tokens[1] == lp_contract.token1(), "token1 address incorrect"
    assert amounts[0] == expected0, "token0 amount incorrect"
    assert amounts[1] == expected1, "token1 amount incorrect"

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
    
    # Convert amounts to 18 decimals
    amount0_18 = amounts[0] * (10 ** (18 - token0_decimals))
    amount1_18 = amounts[1] * (10 ** (18 - token1_decimals))
    
    # Calculate expected total value
    expected_total = (amount0_18 * expected_price0 + amount1_18 * expected_price1) // 1e18
    actual_total = vault_oracle.calculateTotalValue(amounts, tokens)
    assert abs((actual_total - expected_total)) < 0.0001*10**8, "total value calculation incorrect"

    # Test final vault share price
    share_price = vault_oracle.latestAnswer()
    assert share_price > 0, "share price should be positive"
    assert share_price == int(expected_total), "share price calculation incorrect"

