from brownie import PeggedOracle, accounts, interface


def test_pegged_oracle():
    user = accounts.load("vicuna", "vicuna")
    user_params = {"from": user}

    asset = "0x9F0dF7799f6FDAd409300080cfF680f5A23df4b1"
    pegged_asset = "0x039e2fB66102314Ce7b64Ce5Ce3E5183bc94aD38"
    api3_oracle = "0xEFBA61Ad1B7F785eeAb3EA3B5A717d19Ba8344bb"

    pegged_oracle = PeggedOracle.deploy(
        asset, pegged_asset, api3_oracle, bytes("0x", "utf-8"), 0, user_params
    )

    pegged_asset_price = interface.IOracle(api3_oracle).latestAnswer()
    decimals = interface.IOracle(api3_oracle).decimals()
    pegged_asset_price = pegged_asset_price / 10 ** (decimals - 8)
    share_value = interface.IPeggedAsset(asset).convertToAssets(1e18)
    asset_price = pegged_asset_price * share_value / 1e18

    oracle_answer = pegged_oracle.latestAnswer()
    assert oracle_answer == asset_price
