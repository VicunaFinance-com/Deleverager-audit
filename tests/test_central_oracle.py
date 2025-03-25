from brownie import CentralOracle, SwapXBeefyVaultOracle, accounts, interface

# add test where central oracle is not set


def test_central_oracle_admin():
    user = accounts.load("vicuna", "vicuna")
    other = accounts[1]
    user_params = {"from": user}
    other_params = {"from": other}

    # Deploy central oracle
    central_oracle = CentralOracle.deploy(user_params)
    
    token = "0x6047828dc181963ba44974801FF68e538dA5eaF9"
    oracle = "0x4EBD5796990e36f03273ae8dE992696EeF655e69"
    
    # Test only owner can add tokens
    try:
        central_oracle.addToken(token, oracle, bytes("0x", "utf-8"), 0, other_params)
        assert False, "non-owner should not be able to add tokens"
    except:
        pass
    
    # Owner can add tokens
    central_oracle.addToken(token, oracle, bytes("0x", "utf-8"), 0, user_params)
    assert central_oracle.getAssetSource(token) == oracle, "token source not set correctly"

def test_central_oracle_price_types():
    user = accounts.load("vicuna", "vicuna")
    user_params = {"from": user}

    # Deploy central oracle
    central_oracle = CentralOracle.deploy(user_params)
    
    # Test API3
    token = "0x6047828dc181963ba44974801FF68e538dA5eaF9"
    oracle = "0x4EBD5796990e36f03273ae8dE992696EeF655e69"

    central_oracle.addToken(token, oracle, bytes("0x", "utf-8"), 0, user_params)  # API3
    price = central_oracle.getAssetPrice(token)
    assert price > 0, "API3 price should be positive"

    
    # Test Pyth
    token = "0x6047828dc181963ba44974801FF68e538dA5eaF9"
    oracle = "0x2880aB155794e7179c9eE2e38200202908C17B43"
    pyth_id = "2b89b9dc8fdf9f34709a5b106b472f0f39bb6ca9ce04b0fd7f2e971688e2e53b"
    central_oracle.addToken(token, oracle, pyth_id, 2, user_params)  # Pyth
    price = central_oracle.getAssetPrice(token)
    assert price > 0, "Pyth price should be positive"
    
    # Test PeggedOracle
    token = "0xE5DA20F15420aD15DE0fa650600aFc998bbE3955"
    oracle = "0x86235363749D25Ac686f64184F9f0d7188A05573"
    central_oracle.addToken(token, oracle, bytes("0x", "utf-8"), 3, user_params)  # PeggedOracle
    price = central_oracle.getAssetPrice(token)
    assert price > 0, "PeggedOracle price should be positive"