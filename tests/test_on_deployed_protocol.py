from brownie import accounts, Pool, interface, UiPoolDataProviderV3, PoolConfigurator
import json




def test_interest_curves():
    user = accounts.load("vicuna", "vicuna")
    user_params = {"from" : user}
    with open("deploy_real.json", "r") as f:
        all_addresses = json.load(f)
    tested_market = "0x6047828dc181963ba44974801ff68e538da5eaf9"  
    OPTIMAL_USAGE_RATIO = 0.9
    VARIABLE_RATE_SLOPE1 = 0.128
    VARIABLE_RATE_SLOPE2 = 4
    SUPPLY_CAP = 400_000
    RESERVE_FACTOR = 1300
    pool_address_provider = all_addresses["PoolAddressesProvider"]
    pool = Pool.at(all_addresses["Pool-Proxy"])
    # configurator = PoolConfigurator.at(all_addresses["PoolConfigurator-Proxy"])
    # new_strategy = all_addresses["Vicuna stable_new"]
    # configurator.setReserveInterestRateStrategyAddress(tested_market, new_strategy, {"from" : user})
    market_whale = accounts.at("0x5e023c31E1d3dCd08a1B3e8c96f6EF8Aa8FcaCd1", True) # largest holder only have 200k USDT, shame
    market_token = interface.IERC20(tested_market)
    market_token.transfer(user, market_token.balanceOf(market_whale), {"from" : market_whale}) # now have 0
    market_token.approve(pool, market_token.balanceOf(user), user_params)
    deposit_amount = 100_000*10**6
    pool.supply(tested_market, deposit_amount, user, 0, user_params)

    # borrow 10%
    pool.borrow(tested_market, deposit_amount//10,2,0, user, user_params)
    # apr should be equal to 10 * 0.128 = 1.28%
    reserves_data = pool.getReserveData(tested_market)
    supply_apr = reserves_data[2]/10**27
    borrow_apr = reserves_data[4]/10**27
    assert borrow_apr == 10*VARIABLE_RATE_SLOPE1 # small difference, must investigate
    assert supply_apr == 10*VARIABLE_RATE_SLOPE1*(1-RESERVE_FACTOR/10**4)

    # supply another token to be able to borrow more
    usdc = interface.IERC20("0x29219dd400f2Bf60E5a23d13Be72B486D4038894")
    usdc_whale = accounts.at("0x322e1d5384aa4ED66AeCa770B95686271de61dc3", True)
    usdc.transfer(user, 200000*10**6, {"from" : usdc_whale})
    usdc.approve(pool, usdc.balanceOf(user), user_params)
    pool.supply(usdc, 200000*10**6, user, 0, user_params)
    pool.borrow(tested_market, deposit_amount//10*8.1,2,0, user, user_params)
    reserves_data = pool.getReserveData(tested_market)
    supply_apr = reserves_data[2]/10**27
    borrow_apr = reserves_data[4]/10**27

    ui_data_provider = UiPoolDataProviderV3.at(all_addresses["UiPoolDataProviderV3"])
    ui_data_provider.getReservesData(pool_address_provider)






