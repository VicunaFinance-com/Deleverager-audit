import logging
import warnings
from typing import Dict, List, Sequence

from brownie import (ZERO_ADDRESS, AaveOracle, AaveProtocolDataProvider,
                     ACLManager, AToken, BorrowLogic, BridgeLogic,
                     ConfiguratorLogic, DefaultReserveInterestRateStrategy,
                     DelegationAwareAToken, EmissionManager, EModeLogic,
                     FlashLoanLogic, LiquidationLogic, Pool,
                     PoolAddressesProvider, PoolAddressesProviderRegistry,
                     PoolConfigurator, PoolLogic, PullRewardsTransferStrategy,
                     ReservesSetupHelper, RewardsController, StableDebtToken,
                     StakedTokenTransferStrategy, SupplyLogic,
                     VariableDebtToken, accounts, web3)

from .constants import StoreId
from .schemas import (DEPLOY_CONFIG, RATE_STRATEGIES, EthereumAddress,
                      ReserveParams, eContractid)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def list_of_dict_to_arg(list_of_dicts: Sequence[Dict]) -> List[List]:
    result = []
    for dict_instance in list_of_dicts:
        result.append(list(dict_instance.values()))
    return result


def init_reserves_by_helper(
    all_addresses,
    reserves_params: Dict[str, ReserveParams],
    token_addresses: Dict[str, EthereumAddress],
    a_token_name_prefix: str,
    stable_debt_token_name_prefix: str,
    variable_debt_token_name_prefix: str,
    symbol_prefix: str,
    admin: EthereumAddress,
    treasury_address: EthereumAddress,
    incentives_controller: EthereumAddress,
):
    pool_address_provider = PoolAddressesProvider.at(
        all_addresses[StoreId.POOL_ADDRESSES_PROVIDER_ID]
    )
    pool = Pool.at(pool_address_provider.getPool())

    init_chunks = 3
    reserve_tokens = []
    reserve_init_decimals = []
    reserve_symbols = []

    init_input_params = []

    strategy_addresses = {}
    strategy_address_per_asset = {}
    a_token_type = {}
    delegation_aware_atoken_impl_address = ""
    a_token_impl_address = ""
    stable_debt_token_impl_address = ""
    variable_debt_token_impl_address = ""

    stable_debt_token_impl_address = all_addresses[StoreId.STABLE_DEBT_TOKEN_IMPL_ID]
    variable_debt_token_impl_address = all_addresses[StoreId.VARIABLE_DEBT_TOKEN_IMPL_ID]
    a_token_impl_address = all_addresses[StoreId.ATOKEN_IMPL_ID]

    delegated_aware_reserves = {
        key: parameters
        for key, parameters in reserves_params.items()
        if parameters.a_token_impl == eContractid.delegation_aware_token
    }

    if len(delegated_aware_reserves):
        delegation_aware_atoken_impl_address = all_addresses[
            StoreId.DELEGATION_AWARE_ATOKEN_IMPL_ID
        ]

    reserves = {
        key: parameters
        for key, parameters in reserves_params.items()
        if parameters.a_token_impl in [eContractid.delegation_aware_token, eContractid.aToken]
    }

    for symbol, parameters in reserves.items():
        if not token_addresses[symbol]:
            warnings.warn(
                f"- Skipping init of {symbol} due token address is not set at markets config"
            )
        pool_reserve = Pool.at(pool).getReserveData(token_addresses[symbol])
        if pool_reserve[8] != ZERO_ADDRESS:
            warnings.warn(f"- Skipping init of {symbol} due is already initialized")
            continue

        strategy = parameters.strategy
        if strategy.name not in strategy_addresses:
            strategy_addresses[strategy.name] = all_addresses[strategy.get_deployment_id()]

        strategy_address_per_asset[symbol] = strategy_addresses[strategy.name]

        logger.info(
            "Strategy address for asset %s: %s", symbol, strategy_address_per_asset[symbol]
        )

        if parameters.a_token_impl == eContractid.aToken:
            a_token_type[symbol] = "generic"
        elif parameters.a_token_impl == eContractid.delegation_aware_token:
            a_token_type[symbol] = "delegation aware"
        reserve_init_decimals.append(parameters.reserve_decimals)
        reserve_tokens.append(token_addresses[symbol])
        reserve_symbols.append(symbol)

    for idx in range(len(reserve_symbols)):
        symbol = reserve_symbols[idx]
        a_token_to_use = (
            a_token_impl_address
            if a_token_type[symbol] == "generic"
            else delegation_aware_atoken_impl_address
        )
        init_input_params.append(
            {
                "a_token_impl": a_token_to_use,
                "stable_debt_token_impl": stable_debt_token_impl_address,
                "variable_debt_token_impl": variable_debt_token_impl_address,
                "underlying_asset_decimals": reserve_init_decimals[idx],
                "interest_rate_strategy_address": strategy_address_per_asset[reserve_symbols[idx]],
                "underlying_asset": reserve_tokens[idx],
                "treasury": treasury_address,
                "incentives_controller": incentives_controller,
                "a_token_name": f"Aave {a_token_name_prefix} {reserve_symbols[idx]}",
                "a_token_symbol": f"a{symbol_prefix}{reserve_symbols[idx]}",
                "variable_debt_token_name": f"Aave {variable_debt_token_name_prefix} Variable Debt {reserve_symbols[idx]}",
                "variable_debt_token_symbol": f"variableDebt{symbol_prefix}{reserve_symbols[idx]}",
                "stable_debt_token_name": f"Aave {stable_debt_token_name_prefix} Stable Debt {reserve_symbols[idx]}",
                "stable_debt_token_symbol": f"stableDebt{symbol_prefix}{reserve_symbols[idx]}",
                "params": "0x10",
            }
        )
        assert len(init_input_params) == idx + 1
    configurator = PoolConfigurator.at(all_addresses[StoreId.POOL_CONFIGURATOR_PROXY_ID])

    for i in range(0, len(init_input_params), init_chunks):
        configurator.initReserves(
            list_of_dict_to_arg(init_input_params[i : i + init_chunks]), {"from": admin}
        )


def configure_reserves_by_helper(
    all_addresses,
    reserves_params: Dict[str, ReserveParams],
    token_addresses: Dict[str, EthereumAddress],
):
    deployer = accounts.load("vicuna", "vicuna")
    deployer_params = {"from": deployer}
    pool_address_provider = PoolAddressesProvider.at(
        all_addresses[StoreId.POOL_ADDRESSES_PROVIDER_ID]
    )
    acl_manager = ACLManager.at(all_addresses[StoreId.ACL_MANAGER_ID])
    reserves_setup_helper = ReservesSetupHelper.at(all_addresses[StoreId.RESERVES_SETUP_HELPER_ID])
    protocol_data_provider = AaveProtocolDataProvider.at(all_addresses[StoreId.POOL_DATA_PROVIDER])

    tokens = []
    symbols = []
    input_params = []

    for asset_symbol, reserve_parameters_values in reserves_params.items():
        if asset_symbol not in token_addresses:
            logger.info(
                f"- Skipping init of {asset_symbol} due token address is not set at markets config"
            )
            continue
        if reserve_parameters_values.base_ltv_as_collateral == "-1":
            continue
        token_address = token_addresses[asset_symbol]

        # returns (
        #   uint256 decimals,
        #   uint256 ltv,
        #   uint256 liquidationThreshold,
        #   uint256 liquidationBonus,
        #   uint256 reserveFactor,
        #   bool usageAsCollateralEnabled,
        #   bool borrowingEnabled,
        #   bool stableBorrowRateEnabled,
        #   bool isActive,
        #   bool isFrozen
        # );
        already_enabled = protocol_data_provider.getReserveConfigurationData(token_address)[5]
        if already_enabled:
            logger.info(f"- Reserve {asset_symbol} is already enabled as collateral, skipping")
            continue

        input_params.append(
            {
                "asset": token_address,
                "baseLTV": reserve_parameters_values.base_ltv_as_collateral,
                "liquidationThreshold": reserve_parameters_values.liquidation_threshold,
                "liquidationBonus": reserve_parameters_values.liquidation_bonus,
                "reserveFactor": reserve_parameters_values.reserve_factor,
                "borrowCap": reserve_parameters_values.borrow_cap,
                "supplyCap": reserve_parameters_values.supply_cap,
                "stableBorrowingEnabled": reserve_parameters_values.stable_borrow_rate_enabled,
                "borrowingEnabled": reserve_parameters_values.borrowing_enabled,
                "flashLoanEnabled": reserve_parameters_values.flash_loan_enabled,
            }
        )
        tokens.append(token_address)
        symbols.append(asset_symbol)

        if tokens:
            # TODO: check thie account here
            acl_admin = deployer
            acl_admin_tx_parameters = {"from": acl_admin}
            acl_manager.addRiskAdmin(reserves_setup_helper.address, acl_admin_tx_parameters)

            enable_chunks = 20
            pool_configurator_address = pool_address_provider.getPoolConfigurator()

            logger.info(
                f"- Configure reserves in {len(range(0, len(input_params), enable_chunks))} txs"
            )
            for i in range(0, len(input_params), enable_chunks):
                symbol_slice = symbols[i : i + enable_chunks]
                input_params_slice = input_params[i : i + enable_chunks]
                reserves_setup_helper.configureReserves(
                    pool_configurator_address,
                    list_of_dict_to_arg(input_params_slice),
                    acl_admin_tx_parameters,
                )
            acl_manager.removeRiskAdmin(reserves_setup_helper, acl_admin_tx_parameters)
    return all_addresses
