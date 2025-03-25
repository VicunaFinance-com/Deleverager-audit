import json

import pytest
import requests
from brownie import (AaveOracle, ACLManager, AutoLeverager, Pool,
                     VariableDebtToken, accounts, interface)
from brownie.network.contract import batch_creation

ODOS_ROUTER = "0xaC041Df48dF9791B0654f1Dbbf2CC8450C5f2e9D"
MAIN_POOL = "0xaa1C02a83362BcE106dFf6eB65282fE8B97A1665"
SUBMARKET_POOL = "0xAC00f2Bd7849f7Ce2C8EEDCe7C962c9535b4c606"

USDC = "0x29219dd400f2Bf60E5a23d13Be72B486D4038894"
USDC_WHALE = "0x322e1d5384aa4ED66AeCa770B95686271de61dc3"

USDT = "0x6047828dc181963ba44974801FF68e538dA5eaF9"
USDT_WHALE = "0x0d13400CC7c46D77a43957fE614ba58C827dfde6"

SCUSD = "0xd3DCe716f3eF535C5Ff8d041c1A41C3bd89b97aE"
SCUSD_WHALE = "0x4D85bA8c3918359c78Ed09581E5bc7578ba932ba"


@pytest.fixture(scope="module")
def fill_markets():
    TEST_USER = accounts[0]
    FEE_RECEIVER = accounts[1]
    for user, token in zip([USDC_WHALE, USDT_WHALE, SCUSD_WHALE], [USDC, USDT, SCUSD]):
        token = interface.IERC20(token)
        user = accounts.at(user, force=True)
        token.approve(SUBMARKET_POOL, 100_000 * 10**6, {"from": user})
        Pool.at(SUBMARKET_POOL).supply(token, 100_000 * 10**6, user, 0, {"from": user})
        token.transfer(TEST_USER, 2000 * 10**6, {"from": user})


@pytest.fixture(scope="module")
def deploy_and_setup():
    deployer = accounts.load("vicuna", "vicuna")
    deployer_params = {"from": deployer}
    TEST_USER = accounts[0]
    FEE_RECEIVER = accounts[1]
    auto_leverager = AutoLeverager.deploy(
        ODOS_ROUTER, SUBMARKET_POOL, MAIN_POOL, FEE_RECEIVER, deployer_params
    )
    with batch_creation():
        auto_leverager.setFee(10, deployer_params)
        acl_manager = ACLManager.at("0xA294D7B099247F684Db0D8d462355896D31D91A6")
        acl_manager.addFlashBorrower(auto_leverager, deployer_params)
    return auto_leverager


def get_magpie_quote(input_token, input_amount, output_token, swapper_address):
    """
    Get a swap quote from MAGPIE API.
    Returns the expected output amount, output value in USD, and the full quote response.
    """

    # Skip extremely small amounts (less than 1e-5 USD)

    quote_url = "https://api.magpiefi.xyz/aggregator/quote"

    # Ensure input amount is an integer
    input_amount = int(input_amount)
    if input_amount <= 0:
        raise ValueError(f"Input amount must be positive, got {input_amount}")

    quote_request_body = {
        "network": "sonic",  # Adjust for the correct chain ID
        "fromTokenAddress": input_token,
        "toTokenAddress": output_token,
        "gasless": "false",
        "sellAmount": input_amount,
        "slippage": 1 / 100,  # Lower slippage for more accurate quotes
        "toAddr": swapper_address,
        "fromAddr": swapper_address,
    }
    response = requests.get(
        quote_url,
        params=quote_request_body,
        timeout=10,  # Add timeout to prevent hanging
    )

    quote = response.json()
    # print(quote)

    if "outAmounts" not in quote or not quote["outAmounts"]:
        raise ValueError(f"Invalid quote response: missing outAmounts: {quote}")

    output_amount = int(quote["outAmounts"][0])

    if "outValues" not in quote or not quote["outValues"]:
        raise ValueError(f"Invalid quote response: missing outValues: {quote}")

    output_value = quote["outValues"][0]

    return output_amount, output_value, quote


def get_odos_quote(input_token, input_amount, output_token, swapper_address):
    """
    Get a swap quote from Odos API.
    Returns the expected output amount, output value in USD, and the full quote response.
    """

    # Skip extremely small amounts (less than 1e-5 USD)

    quote_url = "https://api.odos.xyz/sor/quote/v2"

    # Ensure input amount is an integer
    input_amount = int(input_amount)
    if input_amount <= 0:
        raise ValueError(f"Input amount must be positive, got {input_amount}")

    quote_request_body = {
        "chainId": 146,  # Adjust for the correct chain ID
        "inputTokens": [{"tokenAddress": input_token, "amount": str(input_amount)}],
        "outputTokens": [{"tokenAddress": output_token, "proportion": 1}],
        "slippageLimitPercent": 1,  # Lower slippage for more accurate quotes
        "userAddr": swapper_address,
        "referralCode": 0,
        "disableRFQs": True,
        "compact": True,
    }
    response = requests.post(
        quote_url,
        headers={"Content-Type": "application/json"},
        json=quote_request_body,
        timeout=10,  # Add timeout to prevent hanging
    )

    quote = response.json()
    # print(quote)
    json.dump(quote, open("./quote.json", "w"))

    if "outAmounts" not in quote or not quote["outAmounts"]:
        raise ValueError(f"Invalid quote response: missing outAmounts: {quote}")

    output_amount = int(quote["outAmounts"][0])

    if "outValues" not in quote or not quote["outValues"]:
        raise ValueError(f"Invalid quote response: missing outValues: {quote}")

    output_value = quote["outValues"][0]

    return output_amount, output_value, quote


def assemble_odos_transaction(quote, liquidator_address):
    """
    Assemble a transaction from an Odos quote.
    Returns the assembled transaction data.
    """

    assemble_url = "https://api.odos.xyz/sor/assemble"

    assemble_request_body = {
        "userAddr": liquidator_address,
        "pathId": quote["pathId"],
        "simulate": False,
    }

    response = requests.post(
        assemble_url,
        headers={"Content-Type": "application/json"},
        json=assemble_request_body,
        timeout=10,
    )

    response.raise_for_status()

    transaction = response.json()
    return transaction["transaction"]["data"], transaction


def test_auto_leverage_same_asset(fill_markets, deploy_and_setup):
    # the borrowed token is in the deposit token
    # borrow token = deposit token = scUSD, no swap needed
    # scUSD-USDC pool - scusd side
    TEST_USER = accounts[0]
    FEE_RECEIVER = accounts[1]
    TEST_USER_PARAMS = {"from": TEST_USER}
    vicuna_vault = interface.IBeefyVault("0x6De36C1Af417A438a69d4AAa3655022E52bbC606")
    lp_token = interface.IICHIVault(vicuna_vault.want())
    depositAsset = interface.IERC20(SCUSD)
    borrowAsset = interface.IERC20(SCUSD)
    initial_amount = 1000 * 10**6
    borrow_amount = 4000 * 10**6
    auto_leverager = deploy_and_setup
    pool = Pool.at(SUBMARKET_POOL)
    borrowed_reserve_data = pool.getReserveData(borrowAsset)
    debt_token = VariableDebtToken.at(borrowed_reserve_data[10])
    expected_fee = initial_amount / 1000
    initial_amount_post_fees = initial_amount - expected_fee

    debt_token.approveDelegation(auto_leverager, 2**256 - 1, TEST_USER_PARAMS)
    depositAsset.approve(auto_leverager, initial_amount, TEST_USER_PARAMS)
    input_parameters = [
        depositAsset,
        borrowAsset,
        initial_amount,
        borrow_amount,
        vicuna_vault,
        bytes("0x", encoding="utf-8"),  # no swap needed
    ]

    auto_leverager.leverageDeposit(input_parameters, TEST_USER_PARAMS)

    supplied_reserve_data = pool.getReserveData(vicuna_vault)
    atoken = interface.IERC20(supplied_reserve_data[8])
    # number of atoken amount is in the vicuna vault unit, so cannot compare directly
    # we use the oracle to compare values
    oracle = AaveOracle.at("0x90bc22a6D40d397693286CBad595116CC86D3a9A")
    vicuna_vault_price = oracle.getAssetPrice(vicuna_vault)
    atoken_balance = atoken.balanceOf(TEST_USER)
    usd_value_deposited = atoken_balance * vicuna_vault_price / 10 ** (18 + 8)
    expected_final_usd_value = (initial_amount + borrow_amount) / 10**6
    assert (
        abs(usd_value_deposited - expected_final_usd_value) < expected_final_usd_value * 0.01
    )  # 1% error
    expected_debt_token = borrow_amount
    assert (
        abs(debt_token.balanceOf(TEST_USER) - expected_debt_token) < expected_debt_token * 0.01
    )  # 1% error
    assert depositAsset.balanceOf(FEE_RECEIVER) == initial_amount / 1000


def convert_token_price(amount, token_in, token_out):
    token_in_decimals = interface.IERC20(token_in)
    token_out_decimals = interface.IERC20(token_out)


def scale_to_decimals(amount, token, target_decimals):
    token_in_decimals = interface.IERC20(token)
    if token_in_decimals > target_decimals:
        return int(amount // 10 ** (token_in_decimals - target_decimals))
    else:
        return int(amount * 10 ** (target_decimals - token_in_decimals))


def approx_eq(val1, val2, precision):
    return float(abs(val1 - val2)) / float(val2) < precision


def test_auto_leverage_different_asset(fill_markets, deploy_and_setup):
    # the borrowed token is not the deposit token
    # borrow token =USDT, deposit token = scUSD, swap needed
    # scUSD-USDC pool - scusd side
    TEST_USER = accounts[0]
    FEE_RECEIVER = accounts[1]
    TEST_USER_PARAMS = {"from": TEST_USER}
    vicuna_vault = interface.IBeefyVault("0x6De36C1Af417A438a69d4AAa3655022E52bbC606")
    lp_token = interface.IICHIVault(vicuna_vault.want())
    depositAsset = interface.IERC20(SCUSD)
    borrowAsset = interface.IERC20(USDT)
    initial_amount = 1000 * 10**6
    borrow_amount = 4000 * 10**6
    auto_leverager = deploy_and_setup
    oracle = AaveOracle.at("0x90bc22a6D40d397693286CBad595116CC86D3a9A")
    # get the odos quote asap, to avoind desync between fork and mainnet
    # deposit asset is the asset of the pool, so the flashloan will be for finalamount - initial amount
    expected_fee = initial_amount / 1000
    initial_amount_post_fees = initial_amount - expected_fee

    output_amount, _, quote = get_magpie_quote(
        borrowAsset.address,
        borrow_amount,
        depositAsset.address,
        auto_leverager.address,
    )
    swap_data, data = assemble_odos_transaction(quote, auto_leverager.address)
    pool = Pool.at(SUBMARKET_POOL)
    borrowed_reserve_data = pool.getReserveData(borrowAsset)
    debt_token = VariableDebtToken.at(borrowed_reserve_data[10])
    deposit_out_amount = int(data["outputTokens"][0]["amount"])
    deposit_in_amount = int(data["inputTokens"][0]["amount"])

    debt_token.approveDelegation(auto_leverager, 2**256 - 1, TEST_USER_PARAMS)
    depositAsset.approve(auto_leverager, initial_amount, TEST_USER_PARAMS)
    input_parameters = [
        depositAsset,
        borrowAsset,
        initial_amount,
        borrow_amount,
        vicuna_vault,
        swap_data,
    ]

    auto_leverager.leverageDeposit(input_parameters, TEST_USER_PARAMS)

    supplied_reserve_data = pool.getReserveData(vicuna_vault)
    atoken = interface.IERC20(supplied_reserve_data[8])
    # number of atoken amount is in the vicuna vault unit, so cannot compare directly
    # we use the oracle to compare values
    oracle = AaveOracle.at("0x90bc22a6D40d397693286CBad595116CC86D3a9A")
    vicuna_vault_price = oracle.getAssetPrice(vicuna_vault)
    atoken_balance = atoken.balanceOf(TEST_USER)
    usd_value_deposited = atoken_balance * vicuna_vault_price / 10 ** (18 + 8)

    # collateral_price = oracle.getAssetPrice(borrowAsset)
    # usd_value_borrowed = mint_amount*collateral_price/(10**(6+8))

    expected_final_usd_value = (initial_amount + borrow_amount) / 10**6
    assert (
        abs(usd_value_deposited - expected_final_usd_value) < expected_final_usd_value * 0.01
    )  # 1% error
    expected_debt_token = borrow_amount
    assert (
        abs(debt_token.balanceOf(TEST_USER) - expected_debt_token) < expected_debt_token * 0.01
    )  # 1% error
    assert approx_eq(depositAsset.balanceOf(FEE_RECEIVER), initial_amount / 1e3, 1e-3)


def test_auto_leverage_different_asset_and_not_deposit_asset(fill_markets, deploy_and_setup):
    # the borrowed token is not the deposit token
    # borrow token =USDC, deposit token = USDC, vault deposit token = scUSD, swap needed
    # scUSD-USDC pool - scusd side
    TEST_USER = accounts[0]
    FEE_RECEIVER = accounts[1]
    TEST_USER_PARAMS = {"from": TEST_USER}
    vicuna_vault = interface.IBeefyVault("0x6De36C1Af417A438a69d4AAa3655022E52bbC606")
    lp_token = interface.IICHIVault(vicuna_vault.want())
    depositAsset = interface.IERC20(USDT)
    borrowAsset = interface.IERC20(USDT)
    vault_deposit_asset = interface.IERC20(SCUSD)
    initial_amount = 1000 * 10**6
    borrow_amount = 4000 * 10**6
    auto_leverager = deploy_and_setup
    # get the odos quote asap, to avoind desync between fork and mainnet
    # deposit asset is not the asset of the pool, so the flashloan will be for finalamount, but the swap will be for final amount - initial_amount + fee because the user already supplies initial amount of the borrowed token
    oracle = AaveOracle.at("0x90bc22a6D40d397693286CBad595116CC86D3a9A")
    expected_fee = initial_amount / 1000
    effective_initial_amount = initial_amount - expected_fee
    EPSILON = expected_fee / 10
    output_amount, _, quote = get_odos_quote(
        borrowAsset.address,
        borrow_amount + initial_amount - expected_fee,
        vault_deposit_asset.address,
        auto_leverager.address,
    )
    # assert 0
    swap_data, data = assemble_odos_transaction(quote, auto_leverager.address)
    pool = Pool.at(SUBMARKET_POOL)
    borrowed_reserve_data = pool.getReserveData(borrowAsset)
    debt_token = VariableDebtToken.at(borrowed_reserve_data[10])

    debt_token.approveDelegation(auto_leverager, 2**256 - 1, TEST_USER_PARAMS)
    depositAsset.approve(auto_leverager, initial_amount, TEST_USER_PARAMS)
    input_parameters = [
        depositAsset,
        borrowAsset,
        initial_amount,
        borrow_amount,
        vicuna_vault,
        swap_data,
    ]

    auto_leverager.leverageDeposit(input_parameters, TEST_USER_PARAMS)

    supplied_reserve_data = pool.getReserveData(vicuna_vault)
    atoken = interface.IERC20(supplied_reserve_data[8])
    # number of atoken amount is in the vicuna vault unit, so cannot compare directly
    # we use the oracle to compare values
    oracle = AaveOracle.at("0x90bc22a6D40d397693286CBad595116CC86D3a9A")
    vicuna_vault_price = oracle.getAssetPrice(vicuna_vault)
    atoken_balance = atoken.balanceOf(TEST_USER)
    usd_value_deposited = atoken_balance * vicuna_vault_price / 10 ** (18 + 8)

    # collateral_price = oracle.getAssetPrice(borrowAsset)
    # usd_value_borrowed = mint_amount*collateral_price/(10**(6+8))

    expected_final_usd_value = (initial_amount + borrow_amount) / 10**6
    assert (
        abs(usd_value_deposited - expected_final_usd_value) < expected_final_usd_value * 0.01
    )  # 1% error
    expected_debt_token = borrow_amount
    assert (
        abs(debt_token.balanceOf(TEST_USER) - expected_debt_token) < expected_debt_token * 0.01
    )  # 1% error
    assert depositAsset.balanceOf(FEE_RECEIVER) == initial_amount / 1000


def test_auto_leverage_unhandled_case(fill_markets, deploy_and_setup):
    # the borrowed token is not the deposit token
    # borrow token =USDT, deposit token = scUSD, swap needed
    # scUSD-USDC pool - scusd side
    TEST_USER = accounts[0]
    FEE_RECEIVER = accounts[1]
    TEST_USER_PARAMS = {"from": TEST_USER}
    vicuna_vault = interface.IBeefyVault("0x6De36C1Af417A438a69d4AAa3655022E52bbC606")
    lp_token = interface.IICHIVault(vicuna_vault.want())
    depositAsset = interface.IERC20(USDC)
    borrowAsset = interface.IERC20(SCUSD)
    initial_amount = 1000 * 10**6
    borrow_amount = 4000 * 10**6
    auto_leverager = deploy_and_setup
    oracle = AaveOracle.at("0x90bc22a6D40d397693286CBad595116CC86D3a9A")
    # get the odos quote asap, to avoind desync between fork and mainnet
    # deposit asset is the asset of the pool, so the flashloan will be for finalamount - initial amount
    expected_fee = initial_amount / 1000
    initial_amount_post_fees = initial_amount - expected_fee

    output_amount, _, quote = get_odos_quote(
        depositAsset.address,
        initial_amount_post_fees,
        borrowAsset.address,
        auto_leverager.address,
    )
    swap_data, data = assemble_odos_transaction(quote, auto_leverager.address)
    pool = Pool.at(SUBMARKET_POOL)
    borrowed_reserve_data = pool.getReserveData(borrowAsset)
    debt_token = VariableDebtToken.at(borrowed_reserve_data[10])

    debt_token.approveDelegation(auto_leverager, 2**256 - 1, TEST_USER_PARAMS)
    depositAsset.approve(auto_leverager, initial_amount, TEST_USER_PARAMS)
    input_parameters = [
        depositAsset,
        borrowAsset,
        initial_amount,
        borrow_amount,
        vicuna_vault,
        swap_data,
    ]

    auto_leverager.leverageDeposit(input_parameters, TEST_USER_PARAMS)

    supplied_reserve_data = pool.getReserveData(vicuna_vault)
    atoken = interface.IERC20(supplied_reserve_data[8])
    # number of atoken amount is in the vicuna vault unit, so cannot compare directly
    # we use the oracle to compare values
    oracle = AaveOracle.at("0x90bc22a6D40d397693286CBad595116CC86D3a9A")
    vicuna_vault_price = oracle.getAssetPrice(vicuna_vault)
    atoken_balance = atoken.balanceOf(TEST_USER)
    usd_value_deposited = atoken_balance * vicuna_vault_price / 10 ** (18 + 8)

    # collateral_price = oracle.getAssetPrice(borrowAsset)
    # usd_value_borrowed = mint_amount*collateral_price/(10**(6+8))

    expected_final_usd_value = (initial_amount + borrow_amount) / 10**6
    assert (
        abs(usd_value_deposited - expected_final_usd_value) < expected_final_usd_value * 0.01
    )  # 1% error
    expected_debt_token = borrow_amount
    assert (
        abs(debt_token.balanceOf(TEST_USER) - expected_debt_token) < expected_debt_token * 0.01
    )  # 1% error
    assert approx_eq(depositAsset.balanceOf(FEE_RECEIVER), initial_amount / 1e3, 1e-3)


def test_bad_tokens(fill_markets, deploy_and_setup):
    TEST_USER = accounts[0]
    FEE_RECEIVER = accounts[1]
    TEST_USER_PARAMS = {"from": TEST_USER}
    vicuna_vault = interface.IBeefyVault("0x6De36C1Af417A438a69d4AAa3655022E52bbC606")
    lp_token = interface.IICHIVault(vicuna_vault.want())
    depositAsset = interface.IERC20(USDT)
    borrowAsset = interface.IERC20(USDC)
    vault_deposit_asset = interface.IERC20(SCUSD)
    initial_amount = 1000 * 10**6
    final_amount = 5000 * 10**6
    auto_leverager = deploy_and_setup
    # get the odos quote asap, to avoind desync between fork and mainnet
    # deposit asset is not the asset of the pool, so the flashloan will be for finalamount, but the swap will be for final amount - initial_amount + fee because the user already supplies initial amount of the borrowed token
    expected_fee = initial_amount / 1000
    output_amount, _, quote = get_odos_quote(
        borrowAsset.address,
        final_amount + expected_fee,
        vault_deposit_asset.address,
        auto_leverager.address,
    )
    # assert 0
    swap_data = assemble_odos_transaction(quote, auto_leverager.address)
    pool = Pool.at(SUBMARKET_POOL)
    borrowed_reserve_data = pool.getReserveData(borrowAsset)
    debt_token = VariableDebtToken.at(borrowed_reserve_data[10])

    debt_token.approveDelegation(auto_leverager, 2**256 - 1, TEST_USER_PARAMS)
    depositAsset.approve(auto_leverager, initial_amount, TEST_USER_PARAMS)
    input_parameters = [
        depositAsset,
        borrowAsset,
        initial_amount,
        final_amount,
        vicuna_vault,
        swap_data,
    ]
    try:
        auto_leverager.leverageDeposit(input_parameters, TEST_USER_PARAMS)
        assert 0, "should have reverted"
    except:
        pass


def test_amount_too_high(fill_markets, deploy_and_setup):
    TEST_USER = accounts[0]
    FEE_RECEIVER = accounts[1]
    TEST_USER_PARAMS = {"from": TEST_USER}
    vicuna_vault = interface.IBeefyVault("0x6De36C1Af417A438a69d4AAa3655022E52bbC606")
    lp_token = interface.IICHIVault(vicuna_vault.want())
    depositAsset = interface.IERC20(USDC)
    borrowAsset = interface.IERC20(USDC)
    vault_deposit_asset = interface.IERC20(SCUSD)
    initial_amount = 1000 * 10**6
    final_amount = 10000 * 10**6  # 10x leverage, max is 6.6 with 85% LTV
    auto_leverager = deploy_and_setup
    # get the odos quote asap, to avoind desync between fork and mainnet
    # deposit asset is not the asset of the pool, so the flashloan will be for finalamount, but the swap will be for final amount - initial_amount + fee because the user already supplies initial amount of the borrowed token
    expected_fee = initial_amount / 1000
    output_amount, _, quote = get_odos_quote(
        borrowAsset.address,
        final_amount + expected_fee,
        vault_deposit_asset.address,
        auto_leverager.address,
    )
    # assert 0
    swap_data = assemble_odos_transaction(quote, auto_leverager.address)
    pool = Pool.at(SUBMARKET_POOL)
    borrowed_reserve_data = pool.getReserveData(borrowAsset)
    debt_token = VariableDebtToken.at(borrowed_reserve_data[10])

    debt_token.approveDelegation(auto_leverager, 2**256 - 1, TEST_USER_PARAMS)
    depositAsset.approve(auto_leverager, initial_amount, TEST_USER_PARAMS)
    input_parameters = [
        depositAsset,
        borrowAsset,
        initial_amount,
        final_amount,
        vicuna_vault,
        swap_data,
    ]
    try:
        auto_leverager.leverageDeposit(input_parameters, TEST_USER_PARAMS)
        assert 0, "should have reverted"
    except:
        pass
