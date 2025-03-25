import pytest
from brownie import accounts, chain, Contract, VeNFT, OptimizedMultiRewardVeNFTStaking, ERC20Mock
import time
from decimal import Decimal

# Constants for testing
MAX_LOCK_DURATION = 730 * 24 * 60 * 60  # 730 days in seconds
MONTH = 30 * 24 * 60 * 60  # 30 days in seconds
PRECISION = 10**18

@pytest.fixture(scope="module")
def lp_token():
    """Deploy a mock ERC20 token to use as LP token"""
    return ERC20Mock.deploy("Mock LP", "LP", 18, {'from': accounts[0]})

@pytest.fixture(scope="module")
def reward_token1():
    """Deploy a mock ERC20 token to use as reward token 1"""
    return ERC20Mock.deploy("Reward Token 1", "RT1", 18, {'from': accounts[0]})

@pytest.fixture(scope="module")
def reward_token2():
    """Deploy a mock ERC20 token to use as reward token 2"""
    return ERC20Mock.deploy("Reward Token 2", "RT2", 18, {'from': accounts[0]})

@pytest.fixture(scope="module")
def ve_nft(lp_token):
    """Deploy the VeNFT contract"""
    return VeNFT.deploy(lp_token.address, {'from': accounts[0]})

@pytest.fixture(scope="module")
def staking_contract(ve_nft):
    """Deploy the OptimizedMultiRewardVeNFTStaking contract"""
    return OptimizedMultiRewardVeNFTStaking.deploy(ve_nft.address, {'from': accounts[0]})

@pytest.fixture(scope="module")
def setup_rewards(staking_contract, reward_token1, reward_token2):
    """Setup reward tokens in the staking contract"""
    # Add reward tokens
    staking_contract.addRewardToken(reward_token1.address, 10**17, {'from': accounts[0]})  # 0.1 tokens per second
    staking_contract.addRewardToken(reward_token2.address, 2 * 10**17, {'from': accounts[0]})  # 0.2 tokens per second
    
    # Fund the staking contract with rewards
    reward_token1.mint(accounts[0], 10000 * 10**18, {'from': accounts[0]})
    reward_token2.mint(accounts[0], 20000 * 10**18, {'from': accounts[0]})
    
    reward_token1.approve(staking_contract.address, 10000 * 10**18, {'from': accounts[0]})
    reward_token2.approve(staking_contract.address, 20000 * 10**18, {'from': accounts[0]})
    
    staking_contract.addRewards(reward_token1.address, 10000 * 10**18, {'from': accounts[0]})
    staking_contract.addRewards(reward_token2.address, 20000 * 10**18, {'from': accounts[0]})
    
    return staking_contract

# Helper functions
def create_lock(ve_nft, lp_token, account, amount, duration):
    """Create a veNFT by locking LP tokens"""
    lp_token.mint(account, amount, {'from': account})
    lp_token.approve(ve_nft.address, amount, {'from': account})
    tx = ve_nft.createLock(amount, duration, {'from': account})
    token_id = tx.return_value
    return token_id

def stake_nft(staking_contract, ve_nft, token_id, account):
    """Stake a veNFT in the staking contract"""
    ve_nft.approve(staking_contract.address, token_id, {'from': account})
    staking_contract.stake(token_id, {'from': account})

def test_staking_multiple_nfts(lp_token, ve_nft, staking_contract):
    """Test that a user can stake multiple NFTs"""
    # Create and stake multiple veNFTs
    amount1 = 100 * 10**18
    duration1 = 365 * 24 * 60 * 60  # 1 year
    
    amount2 = 200 * 10**18
    duration2 = 730 * 24 * 60 * 60  # 2 years
    
    token_id1 = create_lock(ve_nft, lp_token, accounts[1], amount1, duration1)
    token_id2 = create_lock(ve_nft, lp_token, accounts[1], amount2, duration2)
    
    # Stake the NFTs
    stake_nft(staking_contract, ve_nft, token_id1, accounts[1])
    stake_nft(staking_contract, ve_nft, token_id2, accounts[1])
    
    # Check that the user has staked two NFTs
    positions = staking_contract.getStakedPositions(accounts[1])
    assert len(positions) == 2
    
    # Check VePower calculation
    vePower = staking_contract.calculateCurrentUserVePower(accounts[1])
    
    # Expected VePower is the sum of the two positions' VePower
    lock_info1, _ = ve_nft.getLockInfo(token_id1)
    lock_info2, _ = ve_nft.getLockInfo(token_id2)
    
    expected1 = amount1 * (lock_info1[3]) // MAX_LOCK_DURATION
    expected2 = amount2 * (lock_info2[3]) // MAX_LOCK_DURATION
    expected = expected1 + expected2
    
    # Allow for small calculation differences
    assert abs(vePower - expected) < 10**10

def test_user_cannot_steal_others_nft(lp_token, ve_nft, staking_contract):
    """Test that users cannot unstake NFTs they don't own"""
    # Create and stake a veNFT
    amount = 100 * 10**18
    duration = 365 * 24 * 60 * 60  # 1 year
    
    token_id = create_lock(ve_nft, lp_token, accounts[1], amount, duration)
    stake_nft(staking_contract, ve_nft, token_id, accounts[1])
    
    # Try to unstake from a different account
    success = True
    try:
        staking_contract.unstake(token_id, {'from': accounts[2]})
    except Exception:
        success = False
    
    assert not success, "Transaction should have failed"
    
    # Verify the NFT is still staked and owned by the original user
    owner = staking_contract.tokenOwners(token_id)
    assert owner == accounts[1]

def test_total_vepower_follows_linear_equation(lp_token, ve_nft, staking_contract):
    """Test that total VePower calculation follows the linear equation model"""
    # Create and stake multiple veNFTs with different accounts
    amount1 = 100 * 10**18
    duration1 = 730 * 24 * 60 * 60  # 2 years
    
    amount2 = 200 * 10**18
    duration2 = 365 * 24 * 60 * 60  # 1 year
    
    token_id1 = create_lock(ve_nft, lp_token, accounts[1], amount1, duration1)
    token_id2 = create_lock(ve_nft, lp_token, accounts[2], amount2, duration2)
    
    stake_nft(staking_contract, ve_nft, token_id1, accounts[1])
    stake_nft(staking_contract, ve_nft, token_id2, accounts[2])
    
    # Get linear model parameters
    model_info = staking_contract.getGlobalVePowerInfo()
    slope_sum = model_info[0]
    offset_sum = model_info[1]
    
    # Check that the initial global VePower matches our expectation
    initial_global_vePower = staking_contract.calculateCurrentTotalVePower()
    
    # Expected VePower based on the linear equation model
    # VePower(t) = offsetSum - slopeSum * t
    current_time = chain.time()
    expected_vePower = offset_sum - slope_sum * current_time
    
    # Allow for small calculation differences
    assert abs(initial_global_vePower - expected_vePower) < 10**10
    
    # Move time forward and check again
    chain.sleep(duration2 // 2)  # Half the duration of the second position
    chain.mine()
    
    # Update the global VePower
    staking_contract.updateGlobalVePower()
    
    # Check global VePower again
    new_global_vePower = staking_contract.calculateCurrentTotalVePower()
    
    # Expected VePower after time passes
    current_time = chain.time()
    expected_vePower = offset_sum - slope_sum * current_time
    
    # Allow for small calculation differences
    assert abs(new_global_vePower - expected_vePower) < 10**10

def test_vepower_decay_over_time(lp_token, ve_nft, staking_contract):
    """Test that VePower decays linearly over time"""
    # Create and stake a veNFT
    amount = 100 * 10**18
    duration = 730 * 24 * 60 * 60  # 2 years (MAX_LOCK_DURATION)
    
    token_id = create_lock(ve_nft, lp_token, accounts[1], amount, duration)
    stake_nft(staking_contract, ve_nft, token_id, accounts[1])
    
    # Check initial VePower (should be equal to amount since duration = MAX_LOCK_DURATION)
    initial_vePower = staking_contract.calculateCurrentUserVePower(accounts[1])
    assert abs(initial_vePower - amount) < 10**10
    
    # Move time forward by 25% of duration
    chain.sleep(duration // 4)
    chain.mine()
    
    # VePower should now be 75% of the original
    vePower_after_25pct = staking_contract.calculateCurrentUserVePower(accounts[1])
    expected = amount * 3 // 4
    assert abs(vePower_after_25pct - expected) < 10**10
    
    # Move time forward by another 25% of duration
    chain.sleep(duration // 4)
    chain.mine()
    
    # VePower should now be 50% of the original
    vePower_after_50pct = staking_contract.calculateCurrentUserVePower(accounts[1])
    expected = amount // 2
    assert abs(vePower_after_50pct - expected) < 10**10

def test_proportional_rewards_to_vepower(lp_token, ve_nft, staking_contract, setup_rewards, reward_token1):
    """Test that users with 10x more VePower get 10x more rewards"""
    # Create and stake two veNFTs with a 1:10 ratio of VePower
    amount1 = 10 * 10**18
    amount2 = 100 * 10**18
    duration = 730 * 24 * 60 * 60  # 2 years
    
    token_id1 = create_lock(ve_nft, lp_token, accounts[1], amount1, duration)
    token_id2 = create_lock(ve_nft, lp_token, accounts[2], amount2, duration)
    
    stake_nft(staking_contract, ve_nft, token_id1, accounts[1])
    stake_nft(staking_contract, ve_nft, token_id2, accounts[2])
    
    # Move time forward to accumulate rewards
    chain.sleep(7 * 24 * 60 * 60)  # 7 days
    chain.mine()
    
    # Check pending rewards
    pending_rewards1 = staking_contract.pendingRewards(accounts[1], reward_token1.address)
    pending_rewards2 = staking_contract.pendingRewards(accounts[2], reward_token1.address)
    
    # Verify reward ratio is close to 1:10
    reward_ratio = pending_rewards2 / pending_rewards1
    assert 9.5 < reward_ratio < 10.5, f"Reward ratio should be ~10, got {reward_ratio}"

def test_daily_claim_vs_one_time_claim(lp_token, ve_nft, staking_contract, setup_rewards, reward_token1):
    """Test that daily claims vs. one-time claim results in same total rewards for identical positions"""
    # Create and stake two identical veNFTs
    amount = 100 * 10**18
    duration = 730 * 24 * 60 * 60  # 2 years
    
    token_id1 = create_lock(ve_nft, lp_token, accounts[1], amount, duration)
    token_id2 = create_lock(ve_nft, lp_token, accounts[2], amount, duration)
    
    stake_nft(staking_contract, ve_nft, token_id1, accounts[1])
    stake_nft(staking_contract, ve_nft, token_id2, accounts[2])
    
    # Strategy: User 1 claims daily, User 2 claims once at the end
    total_claimed_user1 = 0
    
    # Run for 5 days
    for _ in range(5):
        # Advance 1 day
        chain.sleep(24 * 60 * 60)
        chain.mine()
        
        # User 1 claims daily
        balance_before = reward_token1.balanceOf(accounts[1])
        staking_contract.claimRewards(reward_token1.address, {'from': accounts[1]})
        balance_after = reward_token1.balanceOf(accounts[1])
        
        total_claimed_user1 += (balance_after - balance_before)
    
    # User 2 claims everything at once
    balance_before = reward_token1.balanceOf(accounts[2])
    staking_contract.claimRewards(reward_token1.address, {'from': accounts[2]})
    balance_after = reward_token1.balanceOf(accounts[2])
    
    total_claimed_user2 = balance_after - balance_before
    
    # Verify both users received very similar rewards
    # Allow for small differences due to rounding
    difference_percentage = abs(total_claimed_user1 - total_claimed_user2) / total_claimed_user1 * 100
    assert difference_percentage < 0.1, f"Reward difference should be <0.1%, got {difference_percentage}%"

def test_long_term_nonclaimer_retains_rewards(lp_token, ve_nft, staking_contract, setup_rewards, reward_token1):
    """Test that users who don't claim for a long time don't lose rewards while others claim frequently"""
    # Create and stake veNFTs for multiple users
    amount = 100 * 10**18
    duration = 730 * 24 * 60 * 60  # 2 years
    
    # Create three users - one who never claims, two who claim regularly
    token_id1 = create_lock(ve_nft, lp_token, accounts[1], amount, duration)  # Never claims
    token_id2 = create_lock(ve_nft, lp_token, accounts[2], amount, duration)  # Claims regularly
    token_id3 = create_lock(ve_nft, lp_token, accounts[3], amount, duration)  # Claims regularly
    
    stake_nft(staking_contract, ve_nft, token_id1, accounts[1])
    stake_nft(staking_contract, ve_nft, token_id2, accounts[2])
    stake_nft(staking_contract, ve_nft, token_id3, accounts[3])
    
    # Simulate a long period with regular claims by accounts 2 and 3
    for _ in range(10):
        # Advance 7 days
        chain.sleep(7 * 24 * 60 * 60)
        chain.mine()
        
        # Accounts 2 and 3 claim regularly
        staking_contract.claimRewards(reward_token1.address, {'from': accounts[2]})
        staking_contract.claimRewards(reward_token1.address, {'from': accounts[3]})
    
    # Finally, let account 1 claim after a long time
    balance_before = reward_token1.balanceOf(accounts[1])
    staking_contract.claimRewards(reward_token1.address, {'from': accounts[1]})
    balance_after = reward_token1.balanceOf(accounts[1])
    
    account1_total = balance_after - balance_before
    account2_total = reward_token1.balanceOf(accounts[2])
    account3_total = reward_token1.balanceOf(accounts[3])
    
    # Verify that account 1's rewards are similar to the other accounts
    # They should be very similar since all positions were identical
    avg_others = (account2_total + account3_total) / 2
    difference_percentage = abs(account1_total - avg_others) / avg_others * 100
    
    assert difference_percentage < 0.1, f"Non-claimer should receive same rewards, difference: {difference_percentage}%"

def test_rewards_match_expected_calculations(lp_token, ve_nft, staking_contract, setup_rewards, reward_token1):
    """Test that rewards given to users match expected calculations based on reward parameters"""
    # Create and stake a veNFT
    amount = 100 * 10**18
    duration = 730 * 24 * 60 * 60  # 2 years
    
    token_id = create_lock(ve_nft, lp_token, accounts[1], amount, duration)
    stake_nft(staking_contract, ve_nft, token_id, accounts[1])
    
    # Get the reward rate
    token_info = staking_contract.getRewardTokenInfo(reward_token1.address)
    reward_rate = token_info[0]  # rewards per second
    
    # Single staker should get all rewards
    test_period = 3 * 24 * 60 * 60  # 3 days
    
    # Advance time
    chain.sleep(test_period)
    chain.mine()
    
    # Calculate expected rewards: rate * time
    expected_rewards = reward_rate * test_period
    
    # Check actual rewards
    actual_rewards = staking_contract.pendingRewards(accounts[1], reward_token1.address)
    
    # Allow for small differences due to block timestamp variations
    difference = abs(actual_rewards - expected_rewards)
    assert difference < reward_rate * 10, f"Expected ~{expected_rewards}, got {actual_rewards}"
    
    # Claim and verify balance
    balance_before = reward_token1.balanceOf(accounts[1])
    staking_contract.claimRewards(reward_token1.address, {'from': accounts[1]})
    balance_after = reward_token1.balanceOf(accounts[1])
    
    claimed_amount = balance_after - balance_before
    assert abs(claimed_amount - expected_rewards) < reward_rate * 10, "Claimed amount should match expected"

def test_users_cannot_steal_rewards(lp_token, ve_nft, staking_contract, setup_rewards, reward_token1):
    """Test that users cannot steal other users' rewards"""
    # Create and stake veNFTs for two users
    amount = 100 * 10**18
    duration = 730 * 24 * 60 * 60  # 2 years
    
    token_id1 = create_lock(ve_nft, lp_token, accounts[1], amount, duration)
    token_id2 = create_lock(ve_nft, lp_token, accounts[2], amount, duration)
    
    stake_nft(staking_contract, ve_nft, token_id1, accounts[1])
    stake_nft(staking_contract, ve_nft, token_id2, accounts[2])
    
    # Advance time to accumulate rewards
    chain.sleep(7 * 24 * 60 * 60)  # 7 days
    chain.mine()
    
    # Get pending rewards for user 1
    user1_pending = staking_contract.pendingRewards(accounts[1], reward_token1.address)
    assert user1_pending > 0, "User 1 should have pending rewards"
    
    # Try to claim user 1's rewards from user 2's account
    success = True
    try:
        # User 2 tries to claim on behalf of user 1
        staking_contract.claimRewards(reward_token1.address, {'from': accounts[2]})
        # User 2 should only receive their own rewards
        user1_pending_after = staking_contract.pendingRewards(accounts[1], reward_token1.address)
        assert user1_pending_after == user1_pending, "User 1's rewards should not be affected"
    except Exception:
        success = False
    
    assert success, "Transaction should succeed but only claim user's own rewards"
    
    # Now let user 1 claim their rewards
    balance_before = reward_token1.balanceOf(accounts[1])
    staking_contract.claimRewards(reward_token1.address, {'from': accounts[1]})
    balance_after = reward_token1.balanceOf(accounts[1])
    
    # Verify user 1 got their rewards
    assert balance_after - balance_before > 0, "User 1 should receive their rewards"
    assert balance_after - balance_before >= user1_pending * 99 // 100, "User 1 should get full rewards"

def test_unstake_stops_accruing_rewards(lp_token, ve_nft, staking_contract, setup_rewards, reward_token1):
    """Test that unstaking stops accruing rewards"""
    # Create and stake veNFTs
    amount = 100 * 10**18
    duration = 730 * 24 * 60 * 60  # 2 years
    
    token_id = create_lock(ve_nft, lp_token, accounts[1], amount, duration)
    stake_nft(staking_contract, ve_nft, token_id, accounts[1])
    
    # Advance time to accumulate rewards
    chain.sleep(7 * 24 * 60 * 60)  # 7 days
    chain.mine()
    
    # Get pending rewards
    pending_before_unstake = staking_contract.pendingRewards(accounts[1], reward_token1.address)
    assert pending_before_unstake > 0, "Should have pending rewards"
    
    # Unstake
    staking_contract.unstake(token_id, {'from': accounts[1]})
    
    # Record pending rewards right after unstaking
    pending_after_unstake = staking_contract.pendingRewards(accounts[1], reward_token1.address)
    
    # Advance time again
    chain.sleep(7 * 24 * 60 * 60)  # another 7 days
    chain.mine()
    
    # Check pending rewards after time passes
    pending_later = staking_contract.pendingRewards(accounts[1], reward_token1.address)
    
    # Verify no additional rewards accrued after unstaking
    assert pending_later == pending_after_unstake, "Rewards should not increase after unstaking"
    
    # Claim and verify
    balance_before = reward_token1.balanceOf(accounts[1])
    staking_contract.claimRewards(reward_token1.address, {'from': accounts[1]})
    balance_after = reward_token1.balanceOf(accounts[1])
    
    # Verify claimed amount matches pending amount
    assert balance_after - balance_before == pending_after_unstake, "Claimed amount should match pending"

def test_update_reward_rate(lp_token, ve_nft, staking_contract, setup_rewards, reward_token1):
    """Test updating reward rate affects future rewards"""
    # Create and stake a veNFT
    amount = 100 * 10**18
    duration = 730 * 24 * 60 * 60  # 2 years
    
    token_id = create_lock(ve_nft, lp_token, accounts[1], amount, duration)
    stake_nft(staking_contract, ve_nft, token_id, accounts[1])
    
    # Get initial reward rate
    token_info = staking_contract.getRewardTokenInfo(reward_token1.address)
    initial_rate = token_info[0]
    
    # Advance time
    test_period = 3 * 24 * 60 * 60  # 3 days
    chain.sleep(test_period)
    chain.mine()
    
    # Record pending rewards with initial rate
    pending_initial_rate = staking_contract.pendingRewards(accounts[1], reward_token1.address)
    
    # Double the reward rate
    new_rate = initial_rate * 2
    staking_contract.setRewardRate(reward_token1.address, new_rate, {'from': accounts[0]})
    
    # Advance time again with new rate
    chain.sleep(test_period)
    chain.mine()
    
    # Check total pending rewards
    total_pending = staking_contract.pendingRewards(accounts[1], reward_token1.address)
    
    # New rewards should be approximately double the initial rewards
    new_rewards = total_pending - pending_initial_rate
    
    # Allow for small differences due to block timestamp variations
    ratio = new_rewards / pending_initial_rate
    assert 1.9 < ratio < 2.1, f"Rewards should be ~2x after doubling rate, got ratio: {ratio}"

def test_add_rewards_increases_remaining_rewards(lp_token, ve_nft, staking_contract, setup_rewards, reward_token1):
    """Test that adding rewards increases the remaining rewards balance"""
    # Get initial remaining rewards
    token_info_before = staking_contract.getRewardTokenInfo(reward_token1.address)
    initial_remaining = token_info_before[3]
    
    # Add more rewards
    additional_rewards = 1000 * 10**18
    reward_token1.mint(accounts[0], additional_rewards, {'from': accounts[0]})
    reward_token1.approve(staking_contract.address, additional_rewards, {'from': accounts[0]})
    staking_contract.addRewards(reward_token1.address, additional_rewards, {'from': accounts[0]})
    
    # Check remaining rewards after addition
    token_info_after = staking_contract.getRewardTokenInfo(reward_token1.address)
    new_remaining = token_info_after[3]
    
    # Verify increase in remaining rewards
    expected_increase = additional_rewards
    actual_increase = new_remaining - initial_remaining
    
    assert abs(actual_increase - expected_increase) < 10**10, "Remaining rewards should increase by amount added"

def test_global_vepower_decay_matches_sum_of_individual_positions(lp_token, ve_nft, staking_contract):
    """Test that global VePower matches the sum of individual positions' VePower"""
    # Create and stake multiple veNFTs with different accounts and parameters
    positions = [
        {"account": accounts[1], "amount": 100 * 10**18, "duration": MAX_LOCK_DURATION},
        {"account": accounts[2], "amount": 200 * 10**18, "duration": MAX_LOCK_DURATION // 2},
        {"account": accounts[3], "amount": 150 * 10**18, "duration": MAX_LOCK_DURATION // 4},
    ]
    
    token_ids = []
    for pos in positions:
        token_id = create_lock(ve_nft, lp_token, pos["account"], pos["amount"], pos["duration"])
        stake_nft(staking_contract, ve_nft, token_id, pos["account"])
        token_ids.append(token_id)
    
    # Check at different time points
    check_points = [0, MAX_LOCK_DURATION // 8, MAX_LOCK_DURATION // 4, MAX_LOCK_DURATION // 2]
    
    for offset in check_points:
        # Move time forward
        if offset > 0:
            chain.sleep(offset)
            chain.mine()
        
        # Get global VePower
        global_vePower = staking_contract.calculateCurrentTotalVePower()
        
        # Calculate sum of individual VePowers
        individual_sum = 0
        for i, account in enumerate([p["account"] for p in positions]):
            individual_vePower = staking_contract.calculateCurrentUserVePower(account)
            individual_sum += individual_vePower
        
        # Verify global matches sum of individuals (allow small rounding differences)
        assert abs(global_vePower - individual_sum) < 10**10, f"Global VePower should match sum of individuals at offset {offset}"

def test_claim_all_rewards(lp_token, ve_nft, staking_contract, setup_rewards, reward_token1, reward_token2):
    """Test that claimAllRewards function claims from all reward tokens"""
    # Create and stake a veNFT
    amount = 100 * 10**18
    duration = 730 * 24 * 60 * 60  # 2 years
    
    token_id = create_lock(ve_nft, lp_token, accounts[1], amount, duration)
    stake_nft(staking_contract, ve_nft, token_id, accounts[1])
    
    # Advance time to accumulate rewards
    chain.sleep(7 * 24 * 60 * 60)  # 7 days
    chain.mine()
    
    # Check pending rewards for both tokens
    pending_reward1 = staking_contract.pendingRewards(accounts[1], reward_token1.address)
    pending_reward2 = staking_contract.pendingRewards(accounts[1], reward_token2.address)
    
    assert pending_reward1 > 0, "Should have pending rewards for token 1"
    assert pending_reward2 > 0, "Should have pending rewards for token 2"
    
    # Claim all rewards
    balance1_before = reward_token1.balanceOf(accounts[1])
    balance2_before = reward_token2.balanceOf(accounts[1])
    
    staking_contract.claimAllRewards({'from': accounts[1]})
    
    balance1_after = reward_token1.balanceOf(accounts[1])
    balance2_after = reward_token2.balanceOf(accounts[1])
    
    # Verify both tokens were claimed
    claimed1 = balance1_after - balance1_before
    claimed2 = balance2_after - balance2_before
    
    assert abs(claimed1 - pending_reward1) < 10**10, "Should claim correct amount of token 1"
    assert abs(claimed2 - pending_reward2) < 10**10, "Should claim correct amount of token 2"
    
    # Verify no more pending rewards
    pending_after1 = staking_contract.pendingRewards(accounts[1], reward_token1.address)
    pending_after2 = staking_contract.pendingRewards(accounts[1], reward_token2.address)
    
    assert pending_after1 == 0, "No pending rewards should remain for token 1"
    assert pending_after2 == 0, "No pending rewards should remain for token 2"