import json
import pprint
import re

import pytest
import requests
from brownie import (ZERO_ADDRESS, AaveOracle, ACLManager, AutoDeLeverager,
                     AutoLeverager, BeetsVaultOracle, Pool,
                     PoolAddressesProvider, PoolConfigurator,
                     ReservesSetupHelper, SwapXBeefyVaultOracle,
                     VariableDebtToken, accounts, interface)

ODOS_ROUTER = "0xaC041Df48dF9791B0654f1Dbbf2CC8450C5f2e9D"
MAIN_POOL = "0xaa1C02a83362BcE106dFf6eB65282fE8B97A1665"
SUBMARKET_POOL = "0x220fc1bEcC9bbE1a9dD81795F0505cC36E1B2563"

USDC = "0x29219dd400f2Bf60E5a23d13Be72B486D4038894"
USDC_WHALE = "0x322e1d5384aa4ED66AeCa770B95686271de61dc3"

USDT = "0x6047828dc181963ba44974801FF68e538dA5eaF9"
USDT_WHALE = "0x0d13400CC7c46D77a43957fE614ba58C827dfde6"

SCUSD = "0xd3DCe716f3eF535C5Ff8d041c1A41C3bd89b97aE"
SCUSD_WHALE = "0x4D85bA8c3918359c78Ed09581E5bc7578ba932ba"

AAVE_ORACLE = "0x4D18e0D40E059933d00003457481eF9b4C58f803"

BEETS_VAULT = "0xBA12222222228d8Ba445958a75a0704d566BF2C8"

CENTRAL_ORACLE = "0x3BCAfA5402CbF9b8F79AA3a13D20C642bA9a3c25"

MULTISIG = "0xaCAdD458dF075eF4B6F423A83d5153a98DE4eF4A"

beets_stable = {
    "reserve_token": "0x037BB13Fb35dA590d1144B082F4b08Ff7C8c531C",
    "reserve_init_decimals": 18,
    "reserve_symbol": "BeetsRSB",
    "lp_type": "beets",
    "rate_strategy": "Stable submarket",
    "base_ltv": 8500,
    "liquidation_threshold": 8700,
    "liquidation_bonus": 11000,
    "liquidation_protocol_fee": 1000,
    "reserve_factor": 1300,
    "borrow_cap": 0,
    "supply_cap": 1_000_000,
}
TREASURY = "0xad1bB693975C16eC2cEEF65edD540BC735F8608B"


def list_of_dict_to_arg(list_of_dicts):
    result = []
    for dict_instance in list_of_dicts:
        result.append(list(dict_instance.values()))
    return result


@pytest.fixture(scope="module")
def fill_markets():
    TEST_USER = accounts[0]
    FEE_RECEIVER = accounts[1]
    for user, token in zip([USDC_WHALE, USDT_WHALE, SCUSD_WHALE], [USDC, USDT, SCUSD]):
        token = interface.IERC20(token)
        user = accounts.at(user, force=True)
        # token.approve(SUBMARKET_POOL, 100_000 * 10**6, {"from": user})
        # Pool.at(SUBMARKET_POOL).supply(token, 100_000 * 10**6, user, 0, {"from": user})
        token.transfer(TEST_USER, 2000 * 10**6, {"from": user})


@pytest.fixture(scope="module")
def deploy_and_setup_auto_leverager():
    deployer = accounts.load("vicuna", "vicuna")
    deployer_params = {"from": deployer}
    TEST_USER = accounts[0]
    FEE_RECEIVER = accounts[1]
    auto_leverager = AutoLeverager.deploy(
        ODOS_ROUTER,
        SUBMARKET_POOL,
        MAIN_POOL,
        FEE_RECEIVER,
        BEETS_VAULT,
        AAVE_ORACLE,
        deployer_params,
    )
    auto_leverager.setFee(10, deployer_params)
    for asset in [USDC, USDT, SCUSD]:
        auto_leverager.addSupportedAsset(asset, deployer_params)
    auto_leverager.setMaxPriceImpact(100, deployer_params)
    acl_manager = ACLManager.at("0xA294D7B099247F684Db0D8d462355896D31D91A6")
    acl_manager.addFlashBorrower(auto_leverager, deployer_params)
    return auto_leverager


@pytest.fixture(scope="module")
def deploy_and_setup_auto_deleverager():
    deployer = accounts.load("vicuna", "vicuna")
    deployer_params = {"from": deployer}
    FEE_RECEIVER = accounts[1]
    auto_deleverager = AutoDeLeverager.deploy(
        ODOS_ROUTER,
        SUBMARKET_POOL,
        MAIN_POOL,
        FEE_RECEIVER,
        BEETS_VAULT,
        AAVE_ORACLE,
        deployer_params,
    )
    auto_deleverager.setFee(10, deployer_params)
    for token in [USDC, USDT, SCUSD]:
        auto_deleverager.addSupportedAsset(token, 0, deployer_params)
    auto_deleverager.setTokenType("0x6De36C1Af417A438a69d4AAa3655022E52bbC606", 1, deployer_params)
    auto_deleverager.setTokenType("0xb8330F4027b6cb4402C5d02D535c87579cab2477", 1, deployer_params)
    auto_deleverager.setTokenType("0x037BB13Fb35dA590d1144B082F4b08Ff7C8c531C", 2, deployer_params)
    auto_deleverager.setMaxPriceImpact(100, deployer_params)
    acl_manager = ACLManager.at("0xA294D7B099247F684Db0D8d462355896D31D91A6")
    acl_manager.addFlashBorrower(auto_deleverager, deployer_params)
    return auto_deleverager


@pytest.fixture(scope="module")
def add_beets_vault_to_market():
    # add the vault to oracle
    deployer = accounts.at(MULTISIG, force=True)
    deployer_params = {"from": deployer}
    lp_oracle = BeetsVaultOracle.deploy(
        beets_stable["reserve_token"], CENTRAL_ORACLE, deployer_params
    )
    aave_oracle = AaveOracle.at(AAVE_ORACLE)
    # add market
    reserve_symbol = beets_stable["reserve_symbol"]
    init_input_params = {
        "a_token_impl": "0xe16b8f78b11a78DBe3863e483808Cce6d704d52A",
        "stable_debt_token_impl": "0x7736f66413E56ceA406edB9D6f42E0759E942abc",
        "variable_debt_token_impl": "0xEc3D34931f4a58c2247Ab197c52dc12aE7Ed5cfE",
        "underlying_asset_decimals": beets_stable["reserve_init_decimals"],
        "interest_rate_strategy_address": "0xCd50266f48b45a3f163d93d856Ad41c3130CE487",
        "underlying_asset": beets_stable["reserve_token"],
        "treasury": TREASURY,
        "incentives_controller": "0x9e0B19d932CeA8e787088341fccd1C57298f2c91",
        "a_token_name": f"Vicuna Sonic {reserve_symbol}",
        "a_token_symbol": f"vSonic{reserve_symbol}",
        "variable_debt_token_name": f"Vicuna Sonic Variable Debt {reserve_symbol}",
        "variable_debt_token_symbol": f"variableDebtSonic{reserve_symbol}",
        "stable_debt_token_name": f"Vicuna Stable Debt {reserve_symbol}",
        "stable_debt_token_symbol": f"stableDebt{reserve_symbol}",
        "params": "0x10",
    }
    configurator = PoolConfigurator.at("0x0D8D2221AE6a46770639416Aa253a16422cA65Ad")
    configurator.initReserves(list_of_dict_to_arg([init_input_params]), deployer_params)
    acl_manager = ACLManager.at("0x8cA355E030F839E24c081579B1d0F4b1e0C9A8c5")
    reserves_setup_helper = ReservesSetupHelper.at("0x5008b93a3830e0F795ccc4d84be5313d7fC23Fc6")
    # protocol_data_provider = AaveProtocolDataProvider.at("0xe78536507675de30D375C6d2B5dA1a99819Ea9fa")
    base_ltv = beets_stable["base_ltv"]
    liquidation_threshold = beets_stable["liquidation_threshold"]
    liquidation_bonus = beets_stable["liquidation_bonus"]
    reserve_factor = beets_stable["reserve_factor"]
    borrow_cap = beets_stable["borrow_cap"]
    supply_cap = beets_stable["supply_cap"]
    liquidation_protocol_fee = beets_stable["liquidation_protocol_fee"]
    lp_type = beets_stable["lp_type"]
    if lp_type not in ["asset", "pegged"]:
        can_be_borrowed = False
        flashloan_enabled = False
    else:
        can_be_borrowed = True
        flashloan_enabled = True
    setup_init_params = {
        "asset": beets_stable["reserve_token"],
        "baseLTV": base_ltv,
        "liquidationThreshold": liquidation_threshold,
        "liquidationBonus": liquidation_bonus,
        "reserveFactor": reserve_factor,
        "borrowCap": borrow_cap,
        "supplyCap": supply_cap,
        "stableBorrowingEnabled": False,
        "borrowingEnabled": can_be_borrowed,
        "flashLoanEnabled": flashloan_enabled,
    }
    acl_manager.addRiskAdmin(reserves_setup_helper.address, deployer_params)
    pool_address_provider = PoolAddressesProvider.at("0xd01A2DE5e1Dd7a0826D8B3367A82FE12b4A640b8")
    pool_configurator_address = pool_address_provider.getPoolConfigurator()
    reserves_setup_helper.configureReserves(
        pool_configurator_address, list_of_dict_to_arg([setup_init_params]), deployer_params
    )
    configurator.setLiquidationProtocolFee(
        beets_stable["reserve_token"], liquidation_protocol_fee, deployer_params
    )
    aave_oracle.setAssetSources([beets_stable["reserve_token"]], [lp_oracle], deployer_params)


def get_odos_quote(
    input_tokens,
    input_amounts,
    output_token,
    swapper_address,
):
    """
    Get a swap quote from Odos API.
    Returns the expected output amount, output value in USD, and the full quote response.
    """

    quote_url = "https://api.odos.xyz/sor/quote/v2"

    # Ensure input amount is an integer
    input_amounts = [int(input_amount) for input_amount in input_amounts]
    if any(input_amount <= 0 for input_amount in input_amounts):
        raise ValueError(f"Input amount must be positive, got {min(input_amounts)}")

    quote_request_body = {
        "chainId": 146,  # Adjust for the correct chain ID
        "inputTokens": [
            {"tokenAddress": token, "amount": str(int(amount - 10))}
            for token, amount in zip(input_tokens, input_amounts)
            if token != output_token
        ],
        "outputTokens": [{"tokenAddress": output_token, "proportion": 1}],
        "slippageLimitPercent": 5,  # Lower slippage for more accurate quotes
        "userAddr": getattr(swapper_address, "address", swapper_address),
        "referralCode": 0,
        "disableRFQs": True,
        "compact": False,
    }

    response = requests.post(
        quote_url,
        headers={"Content-Type": "application/json"},
        json=quote_request_body,
        timeout=10,  # Add timeout to prevent hanging
    )

    quote = response.json()

    return quote


def assemble_odos_transaction(quote, liquidator_address):
    """
    Assemble a transaction from an Odos quote.
    Returns the assembled transaction data.
    """

    assemble_url = "https://api.odos.xyz/sor/assemble"

    assemble_request_body = {
        "userAddr": getattr(liquidator_address, "address", liquidator_address),
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


def make_swapx_loop_same_asset(
    user,
    auto_leverager,
    vicuna_vault,
    depositAsset,
    borrowAsset,
    initial_amount=1000 * 10**6,
    borrow_amount=4000 * 10**6,
):
    TEST_USER_PARAMS = {"from": user}
    FEE_RECEIVER = accounts[1]

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
        bytes("0x", encoding="utf-8"),  # no swap needed
        0,
        ZERO_ADDRESS,
    ]
    # pprint(input_parameters)

    auto_leverager.leverageDeposit(input_parameters, TEST_USER_PARAMS)


def make_beets_loop_same_asset(
    user,
    auto_leverager,
    vicuna_vault,
    depositAsset,
    borrowAsset,
    vault_deposit_asset,
    initial_amount=1000 * 10**6,
    borrow_amount=4000 * 10**6,
):
    TEST_USER_PARAMS = {"from": user}
    FEE_RECEIVER = accounts[1]

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
        bytes("0x", encoding="utf-8"),  # no swap needed
        0,
        vault_deposit_asset,
    ]
    # pprint(input_parameters)

    auto_leverager.leverageDeposit(input_parameters, TEST_USER_PARAMS)


def test_beets_loop_same_asset(
    deploy_and_setup_auto_deleverager,
    deploy_and_setup_auto_leverager,
    fill_markets,
    add_beets_vault_to_market,
):

    TEST_USER = accounts[0]
    FEE_RECEIVER = accounts[1]

    vicuna_vault = interface.IBeefyVault("0x037BB13Fb35dA590d1144B082F4b08Ff7C8c531C")
    aave_oracle = AaveOracle.at(AAVE_ORACLE)
    oracle = BeetsVaultOracle.at(aave_oracle.getSourceOfAsset(vicuna_vault))
    token = interface.IERC20(SCUSD)
    make_beets_loop_same_asset(
        TEST_USER, deploy_and_setup_auto_leverager, vicuna_vault, token, token, token
    )
    reserve_data_vicuna = Pool.at(SUBMARKET_POOL).getReserveData(vicuna_vault)
    reserve_data_scusd = Pool.at(SUBMARKET_POOL).getReserveData(SCUSD)
    deleverager = deploy_and_setup_auto_deleverager
    atoken = interface.IERC20(reserve_data_vicuna[8])
    debt_token = VariableDebtToken.at(reserve_data_scusd[10])

    user_bal = atoken.balanceOf(TEST_USER)
    amount_to_withdraw = user_bal // 2

    needed_to_flash = deleverager.computeNeedToFlash(token, vicuna_vault, amount_to_withdraw)

    amounts, tokens = oracle.getTokenAmountsForShare(amount_to_withdraw)
    quote = get_odos_quote(tokens, amounts, SCUSD, deleverager)
    swap_params, tx = assemble_odos_transaction(quote, deleverager)
    atoken.approve(deleverager, amount_to_withdraw, {"from": TEST_USER})
    input_data = [atoken, SCUSD, amount_to_withdraw, needed_to_flash, vicuna_vault, swap_params]
    # TODO : need to test the compute need to flash on its own

    debt_token_balance = debt_token.balanceOf(TEST_USER)
    scusd_before = token.balanceOf(TEST_USER)
    hf = Pool.at(SUBMARKET_POOL).getUserAccountData(TEST_USER)[-1]
    deleverager.leverageWithdraw(input_data, {"from": TEST_USER})
    scusd_after = token.balanceOf(TEST_USER)
    assert scusd_after > scusd_before
    assert atoken.balanceOf(TEST_USER) == user_bal - amount_to_withdraw
    assert abs(debt_token_balance - debt_token.balanceOf(TEST_USER) - needed_to_flash) < 100
    hf_after = Pool.at(SUBMARKET_POOL).getUserAccountData(TEST_USER)[-1]
    assert hf_after >= hf
    assert token.balanceOf(FEE_RECEIVER) > 0


def test_swapx_same_asset(
    deploy_and_setup_auto_deleverager, deploy_and_setup_auto_leverager, fill_markets
):

    TEST_USER = accounts[0]
    FEE_RECEIVER = accounts[1]

    vicuna_vault = interface.IBeefyVault("0x6De36C1Af417A438a69d4AAa3655022E52bbC606")
    oracle = SwapXBeefyVaultOracle.at("0x941be5A61Ff443e68DE80eB49b3f8033Be1be2e6")
    token = interface.IERC20(SCUSD)
    make_swapx_loop_same_asset(
        TEST_USER, deploy_and_setup_auto_leverager, vicuna_vault, token, token
    )
    reserve_data_vicuna = Pool.at(SUBMARKET_POOL).getReserveData(vicuna_vault)
    reserve_data_scusd = Pool.at(SUBMARKET_POOL).getReserveData(SCUSD)
    deleverager = deploy_and_setup_auto_deleverager
    atoken = interface.IERC20(reserve_data_vicuna[8])
    debt_token = VariableDebtToken.at(reserve_data_scusd[10])

    user_bal = atoken.balanceOf(TEST_USER)
    amount_to_withdraw = user_bal // 2

    needed_to_flash = deleverager.computeNeedToFlash(token, vicuna_vault, amount_to_withdraw)

    lp_amount = oracle.sharesToLp(amount_to_withdraw)
    amounts, tokens = oracle.getTokenAmounts(lp_amount)
    quote = get_odos_quote(tokens, amounts, SCUSD, deleverager)
    swap_params, tx = assemble_odos_transaction(quote, deleverager)
    atoken.approve(deleverager, amount_to_withdraw, {"from": TEST_USER})
    input_data = [atoken, SCUSD, amount_to_withdraw, needed_to_flash, vicuna_vault, swap_params]
    # TODO : need to test the compute need to flash on its own

    debt_token_balance = debt_token.balanceOf(TEST_USER)
    scusd_before = token.balanceOf(TEST_USER)
    hf = Pool.at(SUBMARKET_POOL).getUserAccountData(TEST_USER)[-1]
    deleverager.leverageWithdraw(input_data, {"from": TEST_USER})
    scusd_after = token.balanceOf(TEST_USER)
    assert scusd_after > scusd_before
    assert atoken.balanceOf(TEST_USER) == user_bal - amount_to_withdraw
    assert abs(debt_token_balance - debt_token.balanceOf(TEST_USER) - needed_to_flash) < 100
    hf_after = Pool.at(SUBMARKET_POOL).getUserAccountData(TEST_USER)[-1]
    assert hf_after >= hf
    assert token.balanceOf(FEE_RECEIVER) > 0

    # TODO : test health factor is stable


def test_swapx_different_asset(
    deploy_and_setup_auto_deleverager, deploy_and_setup_auto_leverager, fill_markets
):

    TEST_USER = accounts.load("vicuna", "vicuna")
    FEE_RECEIVER = accounts[1]

    vicuna_vault = interface.IBeefyVault("0xb8330F4027b6cb4402C5d02D535c87579cab2477")
    oracle = SwapXBeefyVaultOracle.at("0x31c6e42eF90056cE954eFF1356E8F69C5B787fA0")
    token = interface.IERC20(SCUSD)
    reserve_data_vicuna = Pool.at(SUBMARKET_POOL).getReserveData(vicuna_vault)
    reserve_data_scusd = Pool.at(SUBMARKET_POOL).getReserveData(SCUSD)
    deleverager = deploy_and_setup_auto_deleverager
    atoken = interface.IERC20(reserve_data_vicuna[8])
    debt_token = VariableDebtToken.at(reserve_data_scusd[10])

    user_bal = atoken.balanceOf(TEST_USER)
    amount_to_withdraw = user_bal
    needed_to_flash = deleverager.computeNeedToFlash(token, vicuna_vault, amount_to_withdraw)

    lp_amount = oracle.sharesToLp(amount_to_withdraw)
    amounts, tokens = oracle.getTokenAmounts(lp_amount)
    quote = get_odos_quote(tokens, amounts, SCUSD, deleverager)
    swap_params, tx = assemble_odos_transaction(quote, deleverager)
    atoken.approve(deleverager, amount_to_withdraw, {"from": TEST_USER})
    input_data = [atoken, SCUSD, amount_to_withdraw, needed_to_flash, vicuna_vault, swap_params]
    # TODO : need to test the compute need to flash on its own

    scusd_before = token.balanceOf(TEST_USER)
    hf = Pool.at(SUBMARKET_POOL).getUserAccountData(TEST_USER)[-1]
    deleverager.leverageWithdraw(input_data, {"from": TEST_USER})
    scusd_after = token.balanceOf(TEST_USER)
    assert scusd_after > scusd_before
    assert atoken.balanceOf(TEST_USER) == user_bal - amount_to_withdraw
    assert debt_token.balanceOf(TEST_USER) == 0
    hf_after = Pool.at(SUBMARKET_POOL).getUserAccountData(TEST_USER)[-1]
    assert hf_after >= hf
    assert token.balanceOf(FEE_RECEIVER) > 0
    # TODO : test health factor is stable


def test_auto_deleverager_exploiter_call_flash_loan(
    deploy_and_setup_auto_deleverager, deploy_and_setup_auto_leverager, fill_markets
):

    TEST_USER = accounts.load("vicuna", "vicuna")
    FEE_RECEIVER = accounts[1]

    vicuna_vault = interface.IBeefyVault("0xb8330F4027b6cb4402C5d02D535c87579cab2477")
    oracle = SwapXBeefyVaultOracle.at("0x31c6e42eF90056cE954eFF1356E8F69C5B787fA0")
    token = interface.IERC20(SCUSD)
    reserve_data_vicuna = Pool.at(SUBMARKET_POOL).getReserveData(vicuna_vault)
    reserve_data_scusd = Pool.at(SUBMARKET_POOL).getReserveData(SCUSD)
    deleverager = deploy_and_setup_auto_deleverager
    atoken = interface.IERC20(reserve_data_vicuna[8])
    debt_token = VariableDebtToken.at(reserve_data_scusd[10])

    user_bal = atoken.balanceOf(TEST_USER)
    amount_to_withdraw = user_bal

    atoken.approve(deleverager, amount_to_withdraw, {"from": TEST_USER})
    Pool.at(MAIN_POOL).flashLoan(
        deleverager, [token], [1000 * 10**6], [0], deleverager, "0x0", 0, {"from": TEST_USER}
    )
    # CHECK that the reason for revert is indeed the initiator
    # on anvil : Error: reverted with: revert: Only this contract can initiate the flash loan


def test_pause(deploy_and_setup_auto_deleverager, deploy_and_setup_auto_leverager, fill_markets):

    TEST_USER = accounts.load("vicuna", "vicuna")
    FEE_RECEIVER = accounts[1]

    vicuna_vault = interface.IBeefyVault("0xb8330F4027b6cb4402C5d02D535c87579cab2477")
    oracle = SwapXBeefyVaultOracle.at("0x31c6e42eF90056cE954eFF1356E8F69C5B787fA0")
    token = interface.IERC20(SCUSD)
    reserve_data_vicuna = Pool.at(SUBMARKET_POOL).getReserveData(vicuna_vault)
    reserve_data_scusd = Pool.at(SUBMARKET_POOL).getReserveData(SCUSD)
    deleverager = deploy_and_setup_auto_deleverager
    atoken = interface.IERC20(reserve_data_vicuna[8])
    debt_token = VariableDebtToken.at(reserve_data_scusd[10])

    user_bal = atoken.balanceOf(TEST_USER)
    amount_to_withdraw = user_bal
    needed_to_flash = deleverager.computeNeedToFlash(token, vicuna_vault, amount_to_withdraw)

    lp_amount = oracle.sharesToLp(amount_to_withdraw)
    amounts, tokens = oracle.getTokenAmounts(lp_amount)
    quote = get_odos_quote(tokens, amounts, SCUSD, deleverager)
    swap_params, tx = assemble_odos_transaction(quote, deleverager)
    atoken.approve(deleverager, amount_to_withdraw, {"from": TEST_USER})
    input_data = [atoken, SCUSD, amount_to_withdraw, needed_to_flash, vicuna_vault, swap_params]
    # TODO : need to test the compute need to flash on its own

    scusd_before = token.balanceOf(TEST_USER)
    hf = Pool.at(SUBMARKET_POOL).getUserAccountData(TEST_USER)[-1]
    deleverager.pause({"from": TEST_USER})
    try:
        deleverager.leverageWithdraw(input_data, {"from": TEST_USER})
        assert False, "can't withdraw while paused"
    except:
        pass
    try:
        deleverager.unpause({"from": FEE_RECEIVER})
        assert False, "can't unpause from another account"
    except:
        pass
    deleverager.unpause({"from": TEST_USER})
    deleverager.leverageWithdraw(input_data, {"from": TEST_USER})
    scusd_after = token.balanceOf(TEST_USER)
    assert scusd_after > scusd_before
    assert atoken.balanceOf(TEST_USER) == user_bal - amount_to_withdraw
    assert debt_token.balanceOf(TEST_USER) == 0
    hf_after = Pool.at(SUBMARKET_POOL).getUserAccountData(TEST_USER)[-1]
    assert hf_after >= hf
    assert token.balanceOf(FEE_RECEIVER) > 0
    # TODO : test health factor is stable


def test_max_price_impact(
    deploy_and_setup_auto_deleverager, deploy_and_setup_auto_leverager, fill_markets
):

    TEST_USER = accounts.load("vicuna", "vicuna")
    FEE_RECEIVER = accounts[1]

    vicuna_vault = interface.IBeefyVault("0xb8330F4027b6cb4402C5d02D535c87579cab2477")
    oracle = SwapXBeefyVaultOracle.at("0x31c6e42eF90056cE954eFF1356E8F69C5B787fA0")
    token = interface.IERC20(SCUSD)
    reserve_data_vicuna = Pool.at(SUBMARKET_POOL).getReserveData(vicuna_vault)
    reserve_data_scusd = Pool.at(SUBMARKET_POOL).getReserveData(SCUSD)
    deleverager = deploy_and_setup_auto_deleverager
    atoken = interface.IERC20(reserve_data_vicuna[8])
    debt_token = VariableDebtToken.at(reserve_data_scusd[10])

    user_bal = atoken.balanceOf(TEST_USER)
    amount_to_withdraw = user_bal
    needed_to_flash = deleverager.computeNeedToFlash(token, vicuna_vault, amount_to_withdraw)

    lp_amount = oracle.sharesToLp(amount_to_withdraw)
    amounts, tokens = oracle.getTokenAmounts(lp_amount)
    quote = get_odos_quote(tokens, amounts, SCUSD, deleverager)
    swap_params, tx = assemble_odos_transaction(quote, deleverager)
    atoken.approve(deleverager, amount_to_withdraw, {"from": TEST_USER})
    input_data = [atoken, SCUSD, amount_to_withdraw, needed_to_flash, vicuna_vault, swap_params]
    # TODO : need to test the compute need to flash on its own
    deleverager.setMaxPriceImpact(0, {"from": TEST_USER})
    try:
        deleverager.leverageWithdraw(input_data, {"from": TEST_USER})
        assert False, "can't withdraw with max price impact"
    except:
        pass
