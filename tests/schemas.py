from enum import Enum
from typing import Any, Dict, Optional

from brownie import ZERO_ADDRESS
from pydantic import BaseModel, Field


class IInterestRateStrategyParams(BaseModel):
    name: str
    optimal_usage_ratio: int
    base_variable_borrow_rate: int
    variable_rate_slope1: int
    variable_rate_slope2: int
    stable_rate_slope1: int
    stable_rate_slope2: int
    base_stable_rate_offset: int
    stable_rate_excess_offset: int
    optimal_stable_to_total_debt_ratio: int

    def get_deployment_id(self):
        return f"ReserveStrategy-{self.name}"


def parse_units(value, base_decimals: int):
    return int(float(value) * 10**base_decimals)


rate_strategy_volatile_one = IInterestRateStrategyParams(
    name="rate_strategy_volatile_one",
    optimal_usage_ratio=parse_units("0.45", 27),
    base_variable_borrow_rate=0,
    variable_rate_slope1=parse_units("0.07", 27),
    variable_rate_slope2=parse_units("3", 27),
    stable_rate_slope1=parse_units("0.07", 27),
    stable_rate_slope2=parse_units("3", 27),
    base_stable_rate_offset=parse_units("0.02", 27),
    stable_rate_excess_offset=parse_units("0.05", 27),
    optimal_stable_to_total_debt_ratio=parse_units("0.2", 27),
)

rate_strategy_stable_one = IInterestRateStrategyParams(
    name="rate_strategy_stable_one",
    optimal_usage_ratio=parse_units("0.9", 27),
    base_variable_borrow_rate=parse_units("0", 27),
    variable_rate_slope1=parse_units("0.04", 27),
    variable_rate_slope2=parse_units("0.6", 27),
    stable_rate_slope1=parse_units("0.005", 27),
    stable_rate_slope2=parse_units("0.6", 27),
    base_stable_rate_offset=parse_units("0.01", 27),
    stable_rate_excess_offset=parse_units("0.08", 27),
    optimal_stable_to_total_debt_ratio=parse_units("0.2", 27),
)

rate_strategy_stable_two = IInterestRateStrategyParams(
    name="rate_strategy_stable_two",
    optimal_usage_ratio=parse_units("0.8", 27),
    base_variable_borrow_rate=parse_units("0", 27),
    variable_rate_slope1=parse_units("0.04", 27),
    variable_rate_slope2=parse_units("0.75", 27),
    stable_rate_slope1=parse_units("0.005", 27),
    stable_rate_slope2=parse_units("0.75", 27),
    base_stable_rate_offset=parse_units("0.01", 27),
    stable_rate_excess_offset=parse_units("0.08", 27),
    optimal_stable_to_total_debt_ratio=parse_units("0.2", 27),
)
RATE_STRATEGIES: list[IInterestRateStrategyParams] = [
    rate_strategy_volatile_one,
    rate_strategy_stable_one,
    rate_strategy_stable_two,
]


class eContractid(str, Enum):
    aToken = "aToken"
    delegation_aware_token = "delegation_aware_token"


class ReserveParams(BaseModel):
    strategy: IInterestRateStrategyParams
    base_ltv_as_collateral: str
    liquidation_threshold: str
    liquidation_bonus: str
    liquidation_protocol_fee: str
    borrowing_enabled: bool
    stable_borrow_rate_enabled: bool
    flash_loan_enabled: bool
    reserve_decimals: str
    a_token_impl: eContractid
    reserve_factor: str
    supply_cap: str
    borrow_cap: str
    debt_ceiling: str
    borrowable_isolation: bool


EthereumAddress = str
SymbolMap = Dict[str, str]
TokenAddress = Dict[str, str]
IncentivesConfig = Any
EMode = Any


class BaseConfiguration(BaseModel):
    reserve_factor_treasury_address: EthereumAddress = Field(...)
    reserve_assets: Dict[str, EthereumAddress] = Field(...)
    a_token_name_prefix: str = Field(...)
    stable_debt_token_name_prefix: str = Field(...)
    variable_debt_token_name_prefix: str = Field(...)
    symbol_prefix: str = Field(...)
    reserves_config: Dict[str, ReserveParams] = Field(...)


aave_strategy = ReserveParams(
    strategy=rate_strategy_volatile_one,
    base_ltv_as_collateral="5000",
    liquidation_threshold="6500",
    liquidation_bonus="11000",
    liquidation_protocol_fee="1000",
    borrowing_enabled=True,
    stable_borrow_rate_enabled=False,
    flash_loan_enabled=True,
    reserve_decimals="18",
    a_token_impl=eContractid.aToken,
    reserve_factor="0",
    supply_cap="10000000",
    borrow_cap="8000000",
    debt_ceiling="8000000",
    borrowable_isolation=False,
)
DEPLOY_CONFIG = BaseConfiguration(
    reserve_factor_treasury_address=ZERO_ADDRESS,
    reserve_assets={
        # "AAVE": "0x7Fc66500c84A76Ad7e9c93437bFc5Ac33E2DDaE9",
        # "DAI": "0x6B175474E89094C44Da98b954EedeAC495271d0F",
        # "USDC": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
        "WETH": "0x50c42dEAcD8Fc9773493ED674b675bE577f2634b",
        "ANON": "0x79bbF4508B1391af3A0F4B30bb5FC4aa9ab0E07C",
        # ANON used as useless token for tests
        # "LINK": "0x514910771AF9Ca656af840dff83E8264EcF986CA",
        # Eth example value
    },
    a_token_name_prefix="Etherum",
    stable_debt_token_name_prefix="Etherum",
    variable_debt_token_name_prefix="Etherum",
    symbol_prefix="Eth",
    reserves_config={"WETH": aave_strategy, "ANON": aave_strategy},
)

# class BaseConfiguration(BaseModel):
#     market_id: str = Field(...)
#     a_token_name_prefix: str = Field(...)
#     stable_debt_token_name_prefix: str = Field(...)
#     variable_debt_token_name_prefix: str = Field(...)
#     symbol_prefix: str = Field(...)
#     provider_id: int = Field(...)
#     testnet_market: Optional[bool] = Field(None)
#     provider_registry_owner: Optional[Dict[str, Optional[tEthereumAddress]]] = Field(None)
#     fallback_oracle: Optional[Dict[str, tEthereumAddress]] = Field(None)
#     chainlink_aggregator: Dict[str, TokenAddress] = Field(...)
#     wrapped_token_gateway: Optional[Dict[str, tEthereumAddress]] = Field(None)
#     reserve_factor_treasury_address: Dict[str, tEthereumAddress] = Field(...)
#     stable_debt_token_implementation: Optional[Dict[str, tEthereumAddress]] = Field(None)
#     variable_debt_token_implementation: Optional[Dict[str, tEthereumAddress]] = Field(None)
#     oracle_quote_currency: str = Field(...)
#     oracle_quote_unit: str = Field(...)
#     oracle_quote_currency_address: tEthereumAddress = Field(...)
#     reserves_config: Dict[str, ReserveParams] = Field(...)
#     wrapped_native_token_symbol: str = Field(...)
#     incentives_config: IncentivesConfig = Field(...)
#     e_modes: Dict[str, EMode] = Field(...)
#     l2_pool_enabled: Optional[Dict[str, bool]] = Field(None)
#     stk_aave_proxy: Optional[Dict[str, tEthereumAddress]] = Field(None)
#     paraswap_registry: Optional[Dict[str, tEthereumAddress]] = Field(None)
#     flash_loan_premiums: Dict[str, float] = Field(...)
#     rate_strategies: IInterestRateStrategyParams = Field(...)
