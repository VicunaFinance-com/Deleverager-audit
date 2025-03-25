import json
import logging
import sys
import warnings
from enum import Enum
from pathlib import Path
from typing import Dict, Optional

import pytest
from brownie import (ZERO_ADDRESS, AaveFallbackOracle, AaveOracle,
                     AaveProtocolDataProvider, ACLManager, AToken, BorrowLogic,
                     BridgeLogic, ConfiguratorLogic,
                     DefaultReserveInterestRateStrategy, DelegationAwareAToken,
                     EmissionManager, EModeLogic, FlashLoanLogic,
                     FlashLoanSimpleReceiverBase, LiquidationLogic,
                     MintableERC20, MockOracle, Pool, PoolAddressesProvider,
                     PoolAddressesProviderRegistry, PoolConfigurator,
                     PoolLogic, PullRewardsTransferStrategy,
                     ReservesSetupHelper, RewardsController, StableDebtToken,
                     StakedTokenTransferStrategy, StaticATokenLM, SupplyLogic,
                     VariableDebtToken, accounts, chain, interface, reverts,
                     web3)

# from scripts.deploy_core_protocol import PYTH_ORACLE
from tests.constants import InterestRateMode, OraclesAddresses, StoreId

from .init_helpers import configure_reserves_by_helper, init_reserves_by_helper
from .schemas import (DEPLOY_CONFIG, RATE_STRATEGIES, EthereumAddress,
                      ReserveParams, eContractid)

RESET_INFO = {
    "WETH": {
        "whale": "0x427514a905fa6bEaed9A36E308Fcfa06cE54e95b",
        "reset_amount": 10 * 10**18,
    },
    "ANON": {
        "whale": "0xb3FC32de77d62A35621e48DDf1Aac8C24Be215a6",
        "reset_amount": 10 * 10**18,
    },
}


def is_running_pytest():
    return "pytest" in sys.modules


CACHE_PATH = Path("./test_cache.json")
DEBUG = False
IS_LIVE = False
MOCK_TOKEN_NAME = "ANON"

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


INCENTIVES_EMISSION_MANAGER = ""
INCENTIVES_REWARDS_VAULT = ""
INITIAL_PRICE = 42069 * 10**8


TREASURY = "0xad1bB693975C16eC2cEEF65edD540BC735F8608B"  # multisig

ALL_ADDRESSES = {}


def is_deployed(address):
    address = getattr(address, "address", address)
    result = web3.provider.make_request("eth_getCode", [address, "latest"])["result"]
    return len(result) > 2


@pytest.fixture(scope="module")
def all_addresses():
    try:
        with open(CACHE_PATH, "r") as f:
            ALL_ADDRESSES = json.load(f)
    except:
        ALL_ADDRESSES = {}
        return ALL_ADDRESSES

    if ALL_ADDRESSES:
        address_to_test = ALL_ADDRESSES.get(StoreId.POOL_PROXY_ID)
        if address_to_test is None or not is_deployed(address_to_test):
            ALL_ADDRESSES = {}
            return {}

    return ALL_ADDRESSES


@pytest.fixture(autouse=True, scope="function")
def isolation(deploy_step, fn_isolation):
    pass


def deploy_00(all_addresses):
    deployer = accounts.load("vicuna", "vicuna")
    deployer_params = {"from": deployer}
    # step 00
    registry = PoolAddressesProviderRegistry.deploy(deployer, deployer_params)
    print("Registry", registry.address)
    all_addresses[StoreId.POOL_ADDRESSES_PROVIDER_REGISTRY_ID] = registry.address
    return all_addresses


def deploy_01(all_addresses):
    deployer = accounts.load("vicuna", "vicuna")
    deployer_params = {"from": deployer}
    # step 01
    supply_logic = SupplyLogic.deploy(deployer_params)
    print("SupplyLogic", supply_logic.address)
    all_addresses["SupplyLogic"] = supply_logic.address
    borrow_logic = BorrowLogic.deploy(deployer_params)
    print("BorrowLogic", borrow_logic.address)
    all_addresses["BorrowLogic"] = borrow_logic.address
    liquidation_logic = LiquidationLogic.deploy(deployer_params)
    print("LiquidationLogic", liquidation_logic.address)
    all_addresses["LiquidationLogic"] = liquidation_logic.address
    emode_logic = EModeLogic.deploy(deployer_params)
    print("EModeLogic", emode_logic.address)
    all_addresses["EModeLogic"] = emode_logic.address
    bridge_logic = BridgeLogic.deploy(deployer_params)
    print("BridgeLogic", bridge_logic.address)
    all_addresses["BridgeLogic"] = bridge_logic.address
    configurator_logic = ConfiguratorLogic.deploy(deployer_params)
    print("ConfiguratorLogic", configurator_logic.address)
    all_addresses["ConfiguratorLogic"] = configurator_logic.address
    """await deploy("FlashLoanLogic", {
    from: deployer,
    ...COMMON_DEPLOY_PARAMS,
    libraries: {
      BorrowLogic: borrowLogicArtifact.address,
    },
  });"""
    ### there is a lib passed in params, usually brownie handle that under the hood, but to keep in mind
    flash_loan_logic = FlashLoanLogic.deploy(deployer_params)
    print("FlashLoanLogic", flash_loan_logic.address)
    all_addresses["FlashLoanLogic"] = flash_loan_logic.address
    pool_logic = PoolLogic.deploy(deployer_params)
    print("PoolLogic", pool_logic.address)
    all_addresses["PoolLogic"] = pool_logic.address
    return all_addresses


def get_account(account_address: Optional[str], value_if_empty):
    if isinstance(account_address, str):
        if len(account_address):
            return accounts.at(account_address)
        return accounts.at(getattr(value_if_empty, "address", value_if_empty))
    return account_address


@pytest.fixture(scope="module")
def deploy_step(all_addresses):
    global INCENTIVES_REWARDS_VAULT
    global INCENTIVES_EMISSION_MANAGER

    INCENTIVES_EMISSION_MANAGER = get_account(INCENTIVES_EMISSION_MANAGER, accounts[-1])
    INCENTIVES_REWARDS_VAULT = get_account(INCENTIVES_REWARDS_VAULT, accounts[-2])
    if all_addresses:
        return

    all_addresses = deploy_00(all_addresses)
    all_addresses = deploy_01(all_addresses)
    all_addresses = deploy_20(all_addresses)
    all_addresses = deploy_21a(all_addresses)
    all_addresses = deploy_22(all_addresses)
    all_addresses = deploy_23(all_addresses)
    all_addresses = deploy_24(all_addresses)
    all_addresses = deploy_25(all_addresses)
    all_addresses = deploy_26(all_addresses)
    all_addresses = deploy_27(all_addresses)
    all_addresses = deploy_28(all_addresses)
    all_addresses = deploy_29(all_addresses)
    json.dump(
        {key: getattr(val, "address", val) for key, val in all_addresses.items()},
        open(CACHE_PATH, "w"),
    )

    print(all_addresses)


def deploy_20(all_addresses):
    deployer = accounts.load("vicuna", "vicuna")
    deployer_params = {"from": deployer}
    pool_address_provider = PoolAddressesProvider.deploy("0", deployer, deployer_params)
    pool_address_provider.setMarketId("Vicuna Sonic Markets", deployer_params)
    pool_registry = PoolAddressesProviderRegistry.at(
        all_addresses[StoreId.POOL_ADDRESSES_PROVIDER_REGISTRY_ID]
    )
    provider_id = 1  # not really used except as an id
    pool_registry.registerAddressesProvider(pool_address_provider, provider_id)
    print(StoreId.POOL_ADDRESSES_PROVIDER_ID, pool_address_provider.address)
    all_addresses[StoreId.POOL_ADDRESSES_PROVIDER_ID] = pool_address_provider.address
    pool_data_provider = AaveProtocolDataProvider.deploy(pool_address_provider, deployer_params)
    print(StoreId.POOL_DATA_PROVIDER, pool_data_provider.address)
    all_addresses[StoreId.POOL_DATA_PROVIDER] = pool_data_provider.address
    pool_address_provider.setPoolDataProvider(pool_data_provider, deployer_params)
    return all_addresses


def deploy_21a(all_addresses):
    deployer = accounts.load("vicuna", "vicuna")
    deployer_params = {"from": deployer}
    pool_address_provider = PoolAddressesProvider.at(
        all_addresses[StoreId.POOL_ADDRESSES_PROVIDER_ID]
    )
    pool = Pool.deploy(pool_address_provider, deployer_params)
    pool.initialize(pool_address_provider, deployer_params)
    print("Pool", pool.address)
    all_addresses[StoreId.POOL_IMPL_ID] = pool.address
    return all_addresses


def deploy_22(all_addresses):
    deployer = accounts.load("vicuna", "vicuna")
    deployer_params = {"from": deployer}
    pool_configurator = PoolConfigurator.deploy(deployer_params)
    pool_address_provider = PoolAddressesProvider.at(
        all_addresses[StoreId.POOL_ADDRESSES_PROVIDER_ID]
    )
    pool_configurator.initialize(pool_address_provider, deployer_params)
    print(StoreId.POOL_CONFIGURATOR_IMPL_ID, pool_configurator.address)
    all_addresses[StoreId.POOL_CONFIGURATOR_IMPL_ID] = pool_configurator.address
    reserves_setup_helper = ReservesSetupHelper.deploy(deployer_params)
    print(StoreId.RESERVES_SETUP_HELPER_ID, reserves_setup_helper.address)
    all_addresses[StoreId.RESERVES_SETUP_HELPER_ID] = reserves_setup_helper.address
    return all_addresses


def deploy_23(all_addresses):
    deployer = accounts.load("vicuna", "vicuna")
    deployer_params = {"from": deployer}
    pool_address_provider = PoolAddressesProvider.at(
        all_addresses[StoreId.POOL_ADDRESSES_PROVIDER_ID]
    )
    acl_admin = deployer  # TODO : check
    pool_address_provider.setACLAdmin(acl_admin, deployer_params)
    acl_manager = ACLManager.deploy(pool_address_provider.address, deployer_params)
    print(StoreId.ACL_MANAGER_ID, acl_manager.address)
    all_addresses[StoreId.ACL_MANAGER_ID] = acl_manager.address
    pool_address_provider.setACLManager(acl_manager, deployer_params)
    pool_admin = deployer  # TODO : check
    acl_manager.addPoolAdmin(pool_admin, deployer_params)
    emergency_admin = deployer  # TODO : check
    acl_manager.addEmergencyAdmin(emergency_admin, deployer_params)
    return all_addresses


def deploy_24(all_addresses):
    deployer = accounts.load("vicuna", "vicuna")
    deployer_params = {"from": deployer}
    PYTH_ORACLE = "0x2880aB155794e7179c9eE2e38200202908C17B43"
    base_currency_unit = 100000000

    pool_address_provider = all_addresses[StoreId.POOL_ADDRESSES_PROVIDER_ID]
    fallback_oracle = AaveFallbackOracle.deploy(
        pool_address_provider, PYTH_ORACLE, deployer_params
    )
    all_addresses[StoreId.FALLBACK_ORACLE_ID] = fallback_oracle

    assets_to_sources = {
        asset_address: OraclesAddresses[asset_symbol].value
        for asset_symbol, asset_address in DEPLOY_CONFIG.reserve_assets.items()
        if asset_symbol in OraclesAddresses.__members__
    }
    if not IS_LIVE and is_running_pytest():
        mock_oracle = MockOracle.deploy(INITIAL_PRICE, deployer_params)
        all_addresses["mock_oracle"] = mock_oracle
        assets_to_sources[DEPLOY_CONFIG.reserve_assets[MOCK_TOKEN_NAME]] = mock_oracle

    assets = list(assets_to_sources.keys())
    sources = list(assets_to_sources.values())

    base_currency = ZERO_ADDRESS
    oracle = AaveOracle.deploy(
        pool_address_provider,
        assets,
        sources,
        fallback_oracle,
        base_currency,
        base_currency_unit,
        deployer_params,
    )
    all_addresses[StoreId.ORACLE_ID] = oracle
    assert all([oracle.getSourceOfAsset(token) != ZERO_ADDRESS for token in assets_to_sources])
    return all_addresses


def deploy_25(all_addresses):
    deployer = accounts.load("vicuna", "vicuna")
    deployer_params = {"from": deployer}
    pool_address_provider = PoolAddressesProvider.at(
        all_addresses[StoreId.POOL_ADDRESSES_PROVIDER_ID]
    )
    oracle = all_addresses[StoreId.ORACLE_ID]
    currently_set_oracle = pool_address_provider.getPriceOracle()
    if oracle != currently_set_oracle:
        pool_address_provider.setPriceOracle(oracle, deployer_params)
        logger.debug(f"[Deployment] Added PriceOracle ${oracle} to PoolAddressesProvider")
    else:
        logger.debug("[addresses-provider] Price oracle already set. Skipping tx.")
    return all_addresses


def deploy_26(all_addresses):
    deployer = accounts.load("vicuna", "vicuna")
    deployer_params = {"from": deployer}
    pool_address_provider = all_addresses[StoreId.POOL_ADDRESSES_PROVIDER_ID]
    oracle = all_addresses[StoreId.ORACLE_ID]
    flashloan_premiums_total = 0.0005e4
    flashloan_premiums_protocol = 0.0004e4
    pool = all_addresses[StoreId.POOL_IMPL_ID]
    pool_configurator = all_addresses[StoreId.POOL_CONFIGURATOR_IMPL_ID]
    pool_address_provider = PoolAddressesProvider.at(
        all_addresses[StoreId.POOL_ADDRESSES_PROVIDER_ID]
    )
    is_pool_proxy_pending = pool_address_provider.getPool() == ZERO_ADDRESS
    assert is_pool_proxy_pending

    if is_pool_proxy_pending:
        pool_address_provider.setPoolImpl(pool, deployer_params)
        logger.debug("[Deployment] Attached Pool implementation and deployed proxy contract")

    pool_proxy = pool_address_provider.getPool()
    all_addresses[StoreId.POOL_PROXY_ID] = pool_proxy

    is_pool_configurator_proxy_pending = (
        pool_address_provider.getPoolConfigurator() == ZERO_ADDRESS
    )
    if is_pool_configurator_proxy_pending:
        pool_address_provider.setPoolConfiguratorImpl(pool_configurator, deployer_params)

    pool_configurator_proxy_address = pool_address_provider.getPoolConfigurator()
    all_addresses[StoreId.POOL_CONFIGURATOR_PROXY_ID] = pool_configurator_proxy_address
    pool_configurator = PoolConfigurator.at(pool_configurator_proxy_address)
    pool_configurator.updateFlashloanPremiumTotal(flashloan_premiums_total, deployer_params)
    pool_configurator.updateFlashloanPremiumToProtocol(
        flashloan_premiums_protocol, deployer_params
    )
    return all_addresses


def deploy_27(all_addresses):
    deployer = accounts.load("vicuna", "vicuna")
    deployer_params = {"from": deployer}
    pool_address_provider = PoolAddressesProvider.at(
        all_addresses[StoreId.POOL_ADDRESSES_PROVIDER_ID]
    )
    emission_manager = EmissionManager.deploy(deployer, deployer_params)
    all_addresses[StoreId.EMISSION_MANAGER_ID] = emission_manager

    incentives_impl = RewardsController.deploy(emission_manager, deployer_params)
    all_addresses[StoreId.INCENTIVES_V2_IMPL_ID] = incentives_impl
    incentives_impl.initialize(ZERO_ADDRESS)
    incentives_controller_id = web3.sha3(text="INCENTIVES_CONTROLLER").hex()
    assert (
        incentives_controller_id.lower()
        == "0x703c2c8634bed68d98c029c18f310e7f7ec0e5d6342c590190b3cb8b3ba54532"
    )
    if pool_address_provider.getAddress(incentives_controller_id) == ZERO_ADDRESS:
        pool_address_provider.setAddressAsProxy(
            incentives_controller_id, incentives_impl, deployer_params
        )
        proxy_address = pool_address_provider.getAddress(incentives_controller_id)
        assert proxy_address != ZERO_ADDRESS
        all_addresses[StoreId.INCENTIVES_PROXY_ID] = proxy_address

    rewards_proxy_address = all_addresses[StoreId.INCENTIVES_PROXY_ID]
    emission_manager.setRewardsController(rewards_proxy_address, deployer_params)

    if not IS_LIVE:
        pull_rewards_strategy = PullRewardsTransferStrategy.deploy(
            rewards_proxy_address,
            INCENTIVES_EMISSION_MANAGER,
            INCENTIVES_REWARDS_VAULT,
            deployer_params,
        )
        all_addresses[StoreId.INCENTIVES_PULL_REWARDS_STRATEGY_ID] = pull_rewards_strategy
        staked_aave_address = all_addresses.get(StoreId.STAKE_AAVE_PROXY)
        if staked_aave_address:
            staked_token_transfer_strategy = StakedTokenTransferStrategy.deploy(
                rewards_proxy_address, INCENTIVES_EMISSION_MANAGER, staked_aave_address
            )
            all_addresses[StoreId.INCENTIVES_STAKED_TOKEN_STRATEGY_ID] = (
                staked_token_transfer_strategy
            )
        else:
            warnings.warn(
                """[WARNING] Missing StkAave address. Skipping StakedTokenTransferStrategy deployment."""
            )

    emission_manager.transferOwnership(INCENTIVES_EMISSION_MANAGER, deployer_params)
    return all_addresses


def deploy_28(all_addresses):
    deployer = accounts.load("vicuna", "vicuna")
    deployer_params = {"from": deployer}
    pool_address_provider = PoolAddressesProvider.at(
        all_addresses[StoreId.POOL_ADDRESSES_PROVIDER_ID]
    )
    pool_addr = pool_address_provider.getPool()

    a_token = AToken.deploy(pool_addr, deployer_params)
    all_addresses[StoreId.ATOKEN_IMPL_ID] = a_token.address
    a_token.initialize(
        pool_addr,
        ZERO_ADDRESS,
        ZERO_ADDRESS,
        ZERO_ADDRESS,
        0,
        "ATOKEN_IMPL",
        "ATOKEN_IMPL",
        "0x00",
        deployer_params,
    )

    delegation_aware_a_token = DelegationAwareAToken.deploy(pool_addr, deployer_params)
    all_addresses[StoreId.DELEGATION_AWARE_ATOKEN_IMPL_ID] = delegation_aware_a_token.address

    delegation_aware_a_token.initialize(
        pool_addr,
        ZERO_ADDRESS,
        ZERO_ADDRESS,
        ZERO_ADDRESS,
        0,
        "DELEGATION_AWARE_ATOKEN_IMPL",
        "DELEGATION_AWARE_ATOKEN_IMPL",
        "0x00",
        deployer_params,
    )
    stable_debt_token = StableDebtToken.deploy(pool_addr, deployer_params)
    all_addresses[StoreId.STABLE_DEBT_TOKEN_IMPL_ID] = stable_debt_token.address

    stable_debt_token.initialize(
        pool_addr,
        ZERO_ADDRESS,
        ZERO_ADDRESS,
        0,
        "STABLE_DEBT_TOKEN_IMPL",
        "STABLE_DEBT_TOKEN_IMPL",
        "0x00",
        deployer_params,
    )

    variable_debt_token = VariableDebtToken.deploy(pool_addr, deployer_params)
    all_addresses[StoreId.VARIABLE_DEBT_TOKEN_IMPL_ID] = variable_debt_token

    variable_debt_token.initialize(
        pool_addr,
        ZERO_ADDRESS,
        ZERO_ADDRESS,
        0,
        "VARIABLE_DEBT_TOKEN_IMPL",
        "VARIABLE_DEBT_TOKEN_IMPL",
        "0x00",
        deployer_params,
    )

    return all_addresses


def deploy_29(all_addresses):
    deployer = accounts.load("vicuna", "vicuna")
    deployer_params = {"from": deployer}
    pool_address_provider = PoolAddressesProvider.at(
        all_addresses[StoreId.POOL_ADDRESSES_PROVIDER_ID]
    )

    for strategy in RATE_STRATEGIES:
        reserve_strategy = DefaultReserveInterestRateStrategy.deploy(
            pool_address_provider,
            strategy.optimal_usage_ratio,
            strategy.base_variable_borrow_rate,
            strategy.variable_rate_slope1,
            strategy.variable_rate_slope2,
            strategy.stable_rate_slope1,
            strategy.stable_rate_slope2,
            strategy.base_stable_rate_offset,
            strategy.stable_rate_excess_offset,
            strategy.optimal_stable_to_total_debt_ratio,
            deployer_params,
        )
        all_addresses[strategy.get_deployment_id()] = reserve_strategy.address

    incentives_controller = all_addresses["IncentivesProxy"]
    treasury_address = DEPLOY_CONFIG.reserve_factor_treasury_address
    reserves_addresses = DEPLOY_CONFIG.reserve_assets
    if not reserves_addresses:
        warnings.warn("[WARNING] Skipping initialization. Empty asset list.")
        return

    init_reserves_by_helper(
        all_addresses,
        DEPLOY_CONFIG.reserves_config,
        reserves_addresses,
        DEPLOY_CONFIG.a_token_name_prefix,
        DEPLOY_CONFIG.stable_debt_token_name_prefix,
        DEPLOY_CONFIG.variable_debt_token_name_prefix,
        DEPLOY_CONFIG.symbol_prefix,
        deployer,
        treasury_address,
        incentives_controller,
    )
    configure_reserves_by_helper(all_addresses, DEPLOY_CONFIG.reserves_config, reserves_addresses)
    data_provider = AaveProtocolDataProvider.at(all_addresses[StoreId.POOL_DATA_PROVIDER])
    reserves_config = DEPLOY_CONFIG.reserves_config

    for symbol in reserves_addresses:
        (a_token_address, variable_debt_token_address, stable_debt_token_address) = (
            data_provider.getReserveTokensAddresses(reserves_addresses[symbol])
        )
        all_addresses[f"{symbol}{StoreId.ATOKEN_PREFIX}"] = a_token_address
        all_addresses[f"{symbol}{StoreId.VARIABLE_DEBT_PREFIX}"] = variable_debt_token_address
        all_addresses[f"{symbol}{StoreId.STABLE_DEBT_PREFIX}"] = stable_debt_token_address

    return all_addresses


def test_flashloan(deploy_step, all_addresses: Dict[str, EthereumAddress]):
    user = accounts[0]
    eth_whale = accounts.at("0x431e81E5dfB5A24541b5Ff8762bDEF3f32F96354", True)
    address_provider = PoolAddressesProvider.at(all_addresses[StoreId.POOL_ADDRESSES_PROVIDER_ID])
    pool = Pool.at(address_provider.getPool())
    weth = interface.IERC20(DEPLOY_CONFIG.reserve_assets["WETH"])
    DEPOSIT_AMOUNT = 10 * 10**18
    receiver = FlashLoanSimpleReceiverBase.deploy(address_provider, {"from": user})

    weth.transfer(user, DEPOSIT_AMOUNT, {"from": eth_whale})
    weth.approve(pool.address, DEPOSIT_AMOUNT, {"from": user})
    pool.supply(weth, DEPOSIT_AMOUNT, user, 0, {"from": user})

    weth.transfer(receiver, 10**18, {"from": eth_whale})  # to reimburse premium
    pool.flashLoan(receiver, [weth], [10**18], [0], receiver, "0x00", 0, {"from": user})
    # receiver.call([weth], [10**18], [2], {"from": user})
    atoken = AToken.at(pool.getReserveData(weth)[8])  # atoken holds the amount
    assert weth.balanceOf(atoken) > DEPOSIT_AMOUNT


# @pytest.fixture
def reset_tokens(accounts_to_reset=None):
    accounts_to_reset = accounts_to_reset or [accounts[0], accounts[1]]

    for symbol, data in RESET_INFO.items():
        token = interface.IERC20(DEPLOY_CONFIG.reserve_assets[symbol])
        for account in accounts_to_reset:
            balance = token.balanceOf(account)
            delta = balance - data["reset_amount"]
            whale = accounts.at(data["whale"], True)
            if delta > 0:
                token.transfer(whale, delta, {"from": account})
            else:
                token.transfer(account, -delta, {"from": whale})
            assert token.balanceOf(account) == data["reset_amount"]


def test_liquidation_scenario(deploy_step, all_addresses: Dict[str, EthereumAddress]):

    reset_tokens()

    all_addresses = json.load(open(CACHE_PATH, "r"))
    deployer = accounts.load("vicuna", "vicuna")
    deployer_params = {"from": deployer}

    weth_depositer = accounts[0]
    mock_token_depositer = accounts[1]

    weth_depositer_params = {"from": weth_depositer}
    mock_depositer_params = {"from": mock_token_depositer}

    weth = interface.IERC20(DEPLOY_CONFIG.reserve_assets["WETH"])
    mock_token = interface.IERC20(DEPLOY_CONFIG.reserve_assets[MOCK_TOKEN_NAME])

    address_provider = PoolAddressesProvider.at(all_addresses[StoreId.POOL_ADDRESSES_PROVIDER_ID])
    pool = Pool.at(address_provider.getPool())

    mock_oracle = MockOracle.at(all_addresses["mock_oracle"])
    oracle = AaveOracle.at(all_addresses[StoreId.ORACLE_ID])
    weth_price = oracle.getAssetPrice(weth)
    mock_oracle.setAnswer(weth_price, deployer_params)
    assert oracle.getAssetPrice(mock_token) == weth_price

    DEPOSIT_AMOUNT = 10 * 10**18
    weth.approve(pool.address, DEPOSIT_AMOUNT, weth_depositer_params)
    pool.supply(weth, DEPOSIT_AMOUNT, weth_depositer, 0, weth_depositer_params)
    weth.approve(pool.address, DEPOSIT_AMOUNT, mock_depositer_params)
    pool.supply(weth, DEPOSIT_AMOUNT, mock_token_depositer, 0, mock_depositer_params)

    DEPOSIT_AMOUNT = 10 * 10**18
    mock_token.approve(pool.address, DEPOSIT_AMOUNT, mock_depositer_params)
    pool.supply(mock_token, DEPOSIT_AMOUNT, mock_token_depositer, 0, mock_depositer_params)

    reserve_data_mock = pool.getReserveData(mock_token)
    reserve_data_weth = pool.getReserveData(weth)
    a_token_mock = AToken.at(reserve_data_mock[8])
    a_token_weth = AToken.at(reserve_data_weth[8])

    assert a_token_mock.balanceOf(weth_depositer) == 0
    assert a_token_weth.balanceOf(weth_depositer) == DEPOSIT_AMOUNT

    BORROW_AMOUNT = 5 * 10**18
    before_borrow_mock = mock_token.balanceOf(weth_depositer)
    pool.borrow(
        mock_token,
        BORROW_AMOUNT,
        InterestRateMode.VARIABLE,
        0,
        weth_depositer,
        weth_depositer_params,
    )

    after_borrow_mock = mock_token.balanceOf(weth_depositer)

    mock_debt_token = VariableDebtToken.at(reserve_data_mock[10])
    weth_debt_token = VariableDebtToken.at(reserve_data_weth[10])
    assert after_borrow_mock - before_borrow_mock == BORROW_AMOUNT
    assert mock_debt_token.balanceOf(weth_depositer) == BORROW_AMOUNT
    print(pool.getUserAccountData(weth_depositer))
    mock_oracle.setAnswer(weth_price * 10, deployer_params)
    chain.mine()
    print(pool.getUserAccountData(weth_depositer))
    # assert 0
    # chain.sleep(3600 * 24 * 1000)
    # chain.mine()

    pool.borrow(
        weth,
        BORROW_AMOUNT,
        InterestRateMode.VARIABLE,
        0,
        mock_token_depositer,
        mock_depositer_params,
    )
    to_repay = mock_debt_token.balanceOf(weth_depositer)
    chain.mine()
    user_data = pool.getUserAccountData(weth_depositer)
    assert user_data[-1] < 1e18

    MAX_UINT = 2**256 - 1
    mock_whale = accounts.at(RESET_INFO[MOCK_TOKEN_NAME]["whale"], True)
    mock_token.approve(pool, mock_token.balanceOf(mock_whale), {"from": mock_whale})
    collateral_balance_before = weth.balanceOf(mock_whale)
    weth_deposit_before_liquidation = a_token_weth.balanceOf(
        weth_depositer
    )  # can be DEPOSIT_AMOUNT or higher because of interests
    assert weth_deposit_before_liquidation >= DEPOSIT_AMOUNT
    pool.liquidationCall(weth, mock_token, weth_depositer, MAX_UINT, False, {"from": mock_whale})
    collateral_balance_after = weth.balanceOf(mock_whale)
    assert collateral_balance_after - collateral_balance_before == weth_deposit_before_liquidation
    assert a_token_weth.balanceOf(weth_depositer) == 0
    assert weth_debt_token.balanceOf(weth_depositer) == 0

    # test that the liquidator has been deducted for the correct amount of token used in liquidation and has received the correct amount of token
    # test that the guy being liquidated cannot withdraw the liquidated amount anymore


def test_base_scenario(deploy_step, all_addresses: Dict[str, EthereumAddress]):
    all_addresses = json.load(open(CACHE_PATH, "r"))

    reset_tokens()
    lender_account = accounts[0]
    borrower_account = accounts[1]
    weth = interface.IERC20(DEPLOY_CONFIG.reserve_assets["WETH"])
    # weth.balanceOf(ZERO_ADDRESS)
    eth_whale = accounts.at("0x431e81E5dfB5A24541b5Ff8762bDEF3f32F96354", True)
    address_provider = PoolAddressesProvider.at(all_addresses[StoreId.POOL_ADDRESSES_PROVIDER_ID])
    pool = Pool.at(address_provider.getPool())

    DEPOSIT_AMOUNT = 10 * 10**18
    weth.transfer(lender_account, DEPOSIT_AMOUNT, {"from": eth_whale})
    weth.approve(pool.address, DEPOSIT_AMOUNT, {"from": lender_account})
    pool.supply(weth, DEPOSIT_AMOUNT, lender_account, 0, {"from": lender_account})
    reserve_data = pool.getReserveData(weth)
    atoken = AToken.at(reserve_data[8])
    assert atoken.balanceOf(lender_account) == DEPOSIT_AMOUNT

    BORROW_AMOUNT = 5 * 10**18
    before_borrow = weth.balanceOf(lender_account)
    pool.borrow(weth, BORROW_AMOUNT, 2, 0, lender_account, {"from": lender_account})
    after_borrow = weth.balanceOf(lender_account)
    debt_token = VariableDebtToken.at(reserve_data[10])
    assert after_borrow - before_borrow == BORROW_AMOUNT
    assert debt_token.balanceOf(lender_account) == BORROW_AMOUNT
    chain.sleep(3600 * 6)
    chain.mine()
    to_repay = debt_token.balanceOf(lender_account)
    assert to_repay > BORROW_AMOUNT
    remaining = to_repay - BORROW_AMOUNT
    weth.transfer(lender_account, remaining, {"from": eth_whale})
    weth.approve(pool.address, to_repay, {"from": lender_account})
    pool.repay(weth, to_repay, 2, lender_account, {"from": lender_account})
    assert debt_token.balanceOf(lender_account) < 10**15

    assert atoken.balanceOf(lender_account) > DEPOSIT_AMOUNT  # interest accrued
    before_withdraw = weth.balanceOf(lender_account)
    pool.withdraw(weth, atoken.balanceOf(lender_account), lender_account, {"from": lender_account})
    after_withdraw = weth.balanceOf(lender_account)
    assert after_withdraw - before_withdraw > DEPOSIT_AMOUNT


def test_rewards(deploy_step, all_addresses: Dict[str, EthereumAddress]):
    all_addresses = json.load(open(CACHE_PATH, "r"))
    reset_tokens()
    lender_account = accounts[0]
    borrower_account = accounts[1]
    emission_manager = EmissionManager.at(all_addresses.get(StoreId.EMISSION_MANAGER_ID))
    emission_owner = emission_manager.owner()
    deployer = accounts.load("vicuna", "vicuna")
    deployer_params = {"from": deployer}
    # assert emission_owner == deployer
    reward_token = MintableERC20.deploy(
        f"TEST",
        f"TEST",
        18,
        deployer_params,
    )
    reward_token.mint(deployer, 1_000_000 * 10**18, deployer_params)
    weth = interface.IERC20(DEPLOY_CONFIG.reserve_assets["WETH"])
    # weth.balanceOf(ZERO_ADDRESS)
    eth_whale = accounts.at("0x427514a905fa6bEaed9A36E308Fcfa06cE54e95b", True)
    address_provider = PoolAddressesProvider.at(all_addresses[StoreId.POOL_ADDRESSES_PROVIDER_ID])
    pool = Pool.at(address_provider.getPool())
    reserve_data = pool.getReserveData(weth)
    atoken = AToken.at(reserve_data[8])

    emission_manager.setEmissionAdmin(reward_token, deployer, {"from": emission_owner})
    # reward_token.approve(emission_manager, 1e30, deployer_params)

    reward_oracle = MockOracle.deploy(42424242, deployer_params)
    REWARD_AMOUNT = 100 * 10**18
    rewards_controller = RewardsController.at(emission_manager.getRewardsController())

    transfer_strategy = all_addresses.get(StoreId.INCENTIVES_PULL_REWARDS_STRATEGY_ID)
    asset_params = [
        100,
        REWARD_AMOUNT,
        chain.time() + 3600,
        atoken,
        reward_token,
        transfer_strategy,
        reward_oracle,
    ]
    reward_token.transfer(INCENTIVES_REWARDS_VAULT, REWARD_AMOUNT, deployer_params)
    reward_token.approve(transfer_strategy, REWARD_AMOUNT, {"from": INCENTIVES_REWARDS_VAULT})
    emission_manager.configureAssets([asset_params], deployer_params)
    # return

    DEPOSIT_AMOUNT = 10 * 10**18
    weth.transfer(lender_account, DEPOSIT_AMOUNT, {"from": eth_whale})
    weth.approve(pool.address, DEPOSIT_AMOUNT, {"from": lender_account})
    pool.supply(weth, DEPOSIT_AMOUNT, lender_account, 0, {"from": lender_account})
    assert atoken.balanceOf(lender_account) == DEPOSIT_AMOUNT

    BORROW_AMOUNT = 5 * 10**18
    before_borrow = weth.balanceOf(lender_account)
    pool.borrow(weth, BORROW_AMOUNT, 2, 0, lender_account, {"from": lender_account})
    after_borrow = weth.balanceOf(lender_account)
    debt_token = VariableDebtToken.at(reserve_data[10])
    assert after_borrow - before_borrow == BORROW_AMOUNT
    assert debt_token.balanceOf(lender_account) == BORROW_AMOUNT
    chain.sleep(3600 * 6)
    chain.mine()
    to_repay = debt_token.balanceOf(lender_account)
    assert to_repay > BORROW_AMOUNT
    remaining = to_repay - BORROW_AMOUNT
    weth.transfer(lender_account, remaining, {"from": eth_whale})
    weth.approve(pool.address, to_repay, {"from": lender_account})
    pool.repay(weth, to_repay, 2, lender_account, {"from": lender_account})
    assert debt_token.balanceOf(lender_account) < 10**15

    assert atoken.balanceOf(lender_account) > DEPOSIT_AMOUNT  # interest accrued
    before_withdraw = weth.balanceOf(lender_account)
    rewards_controller.claimAllRewards([atoken], lender_account, {"from": lender_account})

    assert reward_token.balanceOf(lender_account)


def test_erc4626(deploy_step, all_addresses: Dict[str, EthereumAddress]):
    user = accounts[0]
    deployer = accounts.load("vicuna", "vicuna")
    deployer_params = {"from": deployer}
    user_params = {"from": user}
    address_provider = PoolAddressesProvider.at(all_addresses[StoreId.POOL_ADDRESSES_PROVIDER_ID])
    pool = Pool.at(address_provider.getPool())
    weth = interface.IERC20(DEPLOY_CONFIG.reserve_assets["WETH"])
    reserve_data = pool.getReserveData(weth)
    atoken = AToken.at(reserve_data[8])
    erc_wrapper = StaticATokenLM.deploy(pool, ZERO_ADDRESS, deployer_params)
    erc_wrapper.initialize(atoken, "wrapped Atoken", "WATOKEN", deployer_params)
    eth_whale = accounts.at("0x431e81E5dfB5A24541b5Ff8762bDEF3f32F96354", True)
    DEPOSIT_AMOUNT = 10 * 10**18
    weth.transfer(user, DEPOSIT_AMOUNT, {"from": eth_whale})
    weth.approve(erc_wrapper.address, DEPOSIT_AMOUNT, user_params)
    erc_wrapper.deposit(DEPOSIT_AMOUNT, user, user_params)
    assert erc_wrapper.balanceOf(user) == DEPOSIT_AMOUNT
    assert atoken.balanceOf(user) == 0
    assert atoken.balanceOf(erc_wrapper) == DEPOSIT_AMOUNT
    assert erc_wrapper.convertToAssets(DEPOSIT_AMOUNT) == DEPOSIT_AMOUNT

    # deposit and borrow from whale to start interest accrual
    BORROW_AMOUNT = 5 * 10**18
    weth.approve(pool.address, DEPOSIT_AMOUNT, {"from": eth_whale})
    pool.supply(weth, DEPOSIT_AMOUNT, eth_whale, 0, {"from": eth_whale})
    pool.borrow(
        weth, BORROW_AMOUNT, 2, 0, eth_whale, {"from": eth_whale}
    )  # interest starts acrruing
    chain.sleep(3600 * 6)
    chain.mine()
    assert erc_wrapper.balanceOf(user) == DEPOSIT_AMOUNT
    assert atoken.balanceOf(erc_wrapper) > DEPOSIT_AMOUNT
    assert erc_wrapper.convertToAssets(DEPOSIT_AMOUNT) > DEPOSIT_AMOUNT

    # repay and withdraw
    debt_token = VariableDebtToken.at(reserve_data[10])

    to_repay = debt_token.balanceOf(eth_whale)
    weth.approve(pool.address, to_repay, {"from": eth_whale})
    pool.repay(weth, to_repay, 2, eth_whale, {"from": eth_whale})

    before_withdraw = weth.balanceOf(user)
    erc_wrapper.redeem(erc_wrapper.balanceOf(user), user, user, user_params)
    after_withdraw = weth.balanceOf(user)
    assert after_withdraw - before_withdraw > DEPOSIT_AMOUNT
    assert erc_wrapper.balanceOf(user) == 0


def test_erc4626_rewards(deploy_step, all_addresses: Dict[str, EthereumAddress]):
    user = accounts[0]
    deployer = accounts.load("vicuna", "vicuna")
    deployer_params = {"from": deployer}
    user_params = {"from": user}
    late_user = accounts[1]
    late_user_params = {"from": late_user}
    address_provider = PoolAddressesProvider.at(all_addresses[StoreId.POOL_ADDRESSES_PROVIDER_ID])
    pool = Pool.at(address_provider.getPool())
    weth = interface.IERC20(DEPLOY_CONFIG.reserve_assets["WETH"])
    reserve_data = pool.getReserveData(weth)
    atoken = AToken.at(reserve_data[8])
    emission_manager = EmissionManager.at(all_addresses.get(StoreId.EMISSION_MANAGER_ID))
    emission_owner = emission_manager.owner()
    rewards_controller = RewardsController.at(emission_manager.getRewardsController())
    erc_wrapper = StaticATokenLM.deploy(pool, rewards_controller, deployer_params)
    erc_wrapper.initialize(atoken, "wrapped Atoken", "WATOKEN", deployer_params)
    eth_whale = accounts.at("0x427514a905fa6bEaed9A36E308Fcfa06cE54e95b", True)

    REWARD_AMOUNT = 100 * 10**18
    reward_token = MintableERC20.deploy(
        f"TEST",
        f"TEST",
        18,
        deployer_params,
    )
    reward_oracle = MockOracle.deploy(42424242, deployer_params)
    reward_token.mint(deployer, 1_000_000 * 10**18, deployer_params)
    emission_manager.setEmissionAdmin(reward_token, deployer, {"from": emission_owner})

    transfer_strategy = all_addresses.get(StoreId.INCENTIVES_PULL_REWARDS_STRATEGY_ID)
    asset_params = [
        100,
        REWARD_AMOUNT,
        chain.time() + 3600,
        atoken,
        reward_token,
        transfer_strategy,
        reward_oracle,
    ]

    reward_token.transfer(INCENTIVES_REWARDS_VAULT, REWARD_AMOUNT, deployer_params)
    reward_token.approve(transfer_strategy, REWARD_AMOUNT, {"from": INCENTIVES_REWARDS_VAULT})
    emission_manager.configureAssets([asset_params], deployer_params)
    erc_wrapper.refreshRewardTokens(deployer_params)

    DEPOSIT_AMOUNT = 10 * 10**18
    weth.transfer(user, DEPOSIT_AMOUNT, {"from": eth_whale})
    weth.transfer(late_user, DEPOSIT_AMOUNT, {"from": eth_whale})
    weth.approve(erc_wrapper.address, DEPOSIT_AMOUNT, user_params)
    weth.approve(erc_wrapper.address, DEPOSIT_AMOUNT, late_user_params)
    erc_wrapper.deposit(DEPOSIT_AMOUNT, user, user_params)
    assert erc_wrapper.balanceOf(user) == DEPOSIT_AMOUNT
    assert atoken.balanceOf(user) == 0
    assert atoken.balanceOf(erc_wrapper) == DEPOSIT_AMOUNT
    assert erc_wrapper.convertToAssets(DEPOSIT_AMOUNT) == DEPOSIT_AMOUNT

    # deposit and borrow from whale to start interest accrual
    BORROW_AMOUNT = 5 * 10**18
    weth.approve(pool.address, DEPOSIT_AMOUNT, {"from": eth_whale})
    pool.supply(weth, DEPOSIT_AMOUNT, eth_whale, 0, {"from": eth_whale})
    pool.borrow(
        weth, BORROW_AMOUNT, 2, 0, eth_whale, {"from": eth_whale}
    )  # interest starts acrruing
    chain.sleep(3600 * 6)
    chain.mine()
    assert erc_wrapper.balanceOf(user) == DEPOSIT_AMOUNT
    assert atoken.balanceOf(erc_wrapper) > DEPOSIT_AMOUNT
    assert erc_wrapper.convertToAssets(DEPOSIT_AMOUNT) > DEPOSIT_AMOUNT

    # repay and withdraw
    debt_token = VariableDebtToken.at(reserve_data[10])

    to_repay = debt_token.balanceOf(eth_whale)
    weth.approve(pool.address, to_repay, {"from": eth_whale})
    pool.repay(weth, to_repay, 2, eth_whale, {"from": eth_whale})
    erc_wrapper.deposit(DEPOSIT_AMOUNT, late_user, late_user_params)

    erc_wrapper.claimRewards(user, [reward_token], {"from": user})
    assert reward_token.balanceOf(user) > 0
    assert reward_token.balanceOf(late_user) == 0


def test_fallback_oracle(deploy_step, all_addresses):
    deployer = accounts.load("vicuna", "vicuna")
    deployer_params = {"from": deployer}
    oracle = AaveOracle.at(all_addresses[StoreId.ORACLE_ID])
    fallback_oracle = AaveFallbackOracle.at(all_addresses[StoreId.FALLBACK_ORACLE_ID])
    mock_token = accounts[5]
    with reverts("No reliable price source found"):
        weth_price = oracle.getAssetPrice(mock_token)
    fallback_oracle.setAssetSources(
        [mock_token],
        [ZERO_ADDRESS],
        ["0xf490b178d0c85683b7a0f2388b40af2e6f7c90cbe0f96b31f315f08d0e5a2d6d"],
        deployer_params,
    )
    weth_price = oracle.getAssetPrice(mock_token)
    assert weth_price > 0


#

# Test scenario
# Create eth market
# Deposit
# borrow
# Check that deposit got interests
# borrower can repay
# Deposit can be withdraw

# Test scenario 2 (test liqidation)
# Create eth market
# Deposit
# borrow

# Test scenario 3
# Test flashloan


# not used as sonic is not an eth l2
# def deploy_21b(all_addresses):
#     deployer = accounts.load("vicuna", "vicuna")
#     deployer_params = {"from": deployer}
#     pool_address_provider = PoolAddressesProvider.at(all_addresses[StoreId.POOL_ADDRESSES_PROVIDER_ID])
#     pool = Pool.deploy(pool_address_provider, deployer_params)
#     pool.initialize(pool_address_provider, deployer_params)
#     print("Pool", pool.address)
#     all_addresses["Pool"] = pool.address
#     return all_addresses


### TREASURY WILL BE A MULTISIG
# def deploy_treasury(all_addresses):
#     deployer = accounts.load("vicuna", "vicuna")
#     deployer_params = {"from": deployer}
#     # step 11
#     treasury_owner = deployer
#     treasury_proxy = InitializableAdminUpgradeabilityProxy.deploy(deployer_params)
#     treasury_controller = AaveEcosystemReserveController.deploy(treasury_owner, deployer_params)
#     treasury_impl = AaveEcosystemReserveV2.deploy(deployer_params)
#     # treasury_proxy.initialize(treasury_controller, )
