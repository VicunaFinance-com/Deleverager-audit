from enum import Enum

MARKET_NAME = "Test"


class OraclesAddresses(str, Enum):
    WETH = "0x4b13451db620baCC869eA993D9Fb5E1E4CCB5Bf0"
    FALLBACK = None


class InterestRateMode(int, Enum):
    NONE = 0
    STABLE = 1
    VARIABLE = 2


class StoreId(str, Enum):
    IMPL_ID = f"Implementation"
    PROXY_ID = f"Proxy"

    AAVE_COLLECTOR_IMPL_ID = f"AaveCollector-{IMPL_ID}-{MARKET_NAME}"
    AAVE_COLLECTOR_PROXY_ID = f"AaveCollector-{PROXY_ID}-{MARKET_NAME}"
    ACL_MANAGER_ID = f"ACLManager-{MARKET_NAME}"
    ATOKEN_IMPL_ID = f"AToken-{MARKET_NAME}"
    ATOKEN_PREFIX = f"-AToken-{MARKET_NAME}"
    DELEGATION_AWARE_ATOKEN_IMPL_ID = f"DelegationAwareAToken-{MARKET_NAME}"
    EMISSION_MANAGER_ID = f"EmissionManager"
    FALLBACK_ORACLE_ID = f"FallbackOracle-{MARKET_NAME}"
    FAUCET_OWNABLE_ID = f"Faucet-{MARKET_NAME}"
    INCENTIVES_PROXY_ID = f"IncentivesProxy"
    INCENTIVES_PULL_REWARDS_STRATEGY_ID = f"PullRewardsTransferStrategy"
    INCENTIVES_STAKED_TOKEN_STRATEGY_ID = f"StakedTokenTransferStrategy"
    INCENTIVES_V2_IMPL_ID = f"IncentivesV2-{IMPL_ID}"
    L2_ENCODER = f"L2Encoder"
    L2_POOL_IMPL_ID = f"L2Pool-{IMPL_ID}"
    ORACLE_ID = f"AaveOracle-{MARKET_NAME}"
    POOL_ADDRESSES_PROVIDER_ID = f"PoolAddressesProvider-{MARKET_NAME}"
    POOL_ADDRESSES_PROVIDER_REGISTRY_ID = f"PoolAddressesProviderRegistry"
    POOL_CONFIGURATOR_IMPL_ID = f"PoolConfigurator-{IMPL_ID}"
    POOL_CONFIGURATOR_PROXY_ID = f"PoolConfigurator-{PROXY_ID}-{MARKET_NAME}"
    POOL_DATA_PROVIDER = f"PoolDataProvider-{MARKET_NAME}"
    POOL_IMPL_ID = f"Pool-{IMPL_ID}"
    POOL_PROXY_ID = f"Pool-{PROXY_ID}-{MARKET_NAME}"
    RESERVES_SETUP_HELPER_ID = f"ReservesSetupHelper"
    STABLE_DEBT_PREFIX = f"-StableDebtToken-{MARKET_NAME}"
    STABLE_DEBT_TOKEN_IMPL_ID = f"StableDebtToken-{MARKET_NAME}"
    STAKE_AAVE_IMPL_V1 = f"StakeAave-REV-1-{IMPL_ID}"
    STAKE_AAVE_IMPL_V2 = f"StakeAave-REV-2-{IMPL_ID}"
    STAKE_AAVE_IMPL_V3 = f"StakeAave-REV-3-{IMPL_ID}"
    STAKE_AAVE_PROXY = f"StakeAave-{PROXY_ID}"
    TESTNET_PRICE_AGGR_PREFIX = f"-TestnetPriceAggregator-{MARKET_NAME}"
    TESTNET_REWARD_TOKEN_PREFIX = f"-TestnetMintableERC20-Reward-{MARKET_NAME}"
    TESTNET_TOKEN_PREFIX = f"-TestnetMintableERC20-{MARKET_NAME}"
    TREASURY_CONTROLLER_ID = f"Treasury-Controller"
    TREASURY_IMPL_ID = f"Treasury-{IMPL_ID}"
    TREASURY_PROXY_ID = f"TreasuryProxy"
    VARIABLE_DEBT_PREFIX = f"-VariableDebtToken-{MARKET_NAME}"
    VARIABLE_DEBT_TOKEN_IMPL_ID = f"VariableDebtToken-{MARKET_NAME}"
