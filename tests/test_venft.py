import pytest
import time
from brownie import VeNFT, accounts, chain, web3, exceptions, Wei, MintableERC20

# Constants for testing
LP_AMOUNT = Wei("100 ether")
SMALL_LP_AMOUNT = Wei("10 ether")
ONE_DAY = 86400  # seconds
ONE_MONTH = 30 * ONE_DAY
MAX_LOCK = 730 * ONE_DAY  # 2 years (730 days)
HALF_LOCK = 365 * ONE_DAY  # 1 year


@pytest.fixture(scope="module")
def lp_token(MintableERC20, accounts):
    """Deploy a test ERC20 token for LP"""
    return MintableERC20.deploy("hh", "hh", 18,  {'from': accounts[0]})


@pytest.fixture(scope="module")
def ve_nft(VeNFT, lp_token, accounts):
    """Deploy the VeNFT contract"""
    return VeNFT.deploy(lp_token.address, {'from': accounts[0]})


@pytest.fixture(scope="function")
def setup(lp_token, ve_nft, accounts):
    """Setup for each test - mint LP tokens to users"""
    # Mint LP tokens to first 3 accounts
    for i in range(3):
        lp_token.mint(accounts[i], LP_AMOUNT * 10, {'from': accounts[0]})
        lp_token.approve(ve_nft.address, LP_AMOUNT * 10, {'from': accounts[i]})
    
    return lp_token, ve_nft


def test_create_lock(setup, accounts):
    """Test creating a lock with various durations and ensure correct vePower calculation
    and LP token transfer"""
    lp_token, ve_nft = setup
    
    # Check initial LP token balances
    initial_lp_balance = lp_token.balanceOf(accounts[0])
    initial_contract_balance = lp_token.balanceOf(ve_nft.address)
    
    # Create a lock for maximum duration (2 years)
    tx = ve_nft.createLock(LP_AMOUNT, MAX_LOCK, {'from': accounts[0]})
    token_id = tx.return_value
    
    # Check LP tokens were transferred from user to contract
    assert lp_token.balanceOf(accounts[0]) == initial_lp_balance - LP_AMOUNT
    assert lp_token.balanceOf(ve_nft.address) == initial_contract_balance + LP_AMOUNT
    
    # Check lock information
    lock_info, ve_power = ve_nft.getLockInfo(token_id)
    assert lock_info[0] == LP_AMOUNT  # amount
    assert lock_info[3] == MAX_LOCK  # lockDuration
    assert ve_power == LP_AMOUNT  # For max lock, vePower = amount
    
    # Create a lock for half duration (1 year)
    initial_lp_balance_2 = lp_token.balanceOf(accounts[1])
    initial_contract_balance_2 = lp_token.balanceOf(ve_nft.address)
    
    tx2 = ve_nft.createLock(LP_AMOUNT, HALF_LOCK, {'from': accounts[1]})
    token_id2 = tx2.return_value
    
    # Check LP tokens were transferred again
    assert lp_token.balanceOf(accounts[1]) == initial_lp_balance_2 - LP_AMOUNT
    assert lp_token.balanceOf(ve_nft.address) == initial_contract_balance_2 + LP_AMOUNT
    
    # Check lock information and vePower (should be half of max)
    lock_info2, ve_power2 = ve_nft.getLockInfo(token_id2)
    assert lock_info2[0] == LP_AMOUNT
    assert lock_info2[3] == HALF_LOCK
    # For half duration, vePower = amount * 0.5
    assert ve_power2 == LP_AMOUNT // 2 


def test_extend_lock(setup, accounts):
    """Test extending a lock and verify the new vePower is calculated correctly 
    while ensuring LP tokens remain locked"""
    lp_token, ve_nft = setup
    
    # Track initial LP balances
    initial_user_balance = lp_token.balanceOf(accounts[0])
    initial_contract_balance = lp_token.balanceOf(ve_nft.address)
    
    # Create a lock for half duration
    tx = ve_nft.createLock(LP_AMOUNT, HALF_LOCK, {'from': accounts[0]})
    token_id = tx.return_value
    
    # Verify LP tokens were transferred
    assert lp_token.balanceOf(accounts[0]) == initial_user_balance - LP_AMOUNT
    assert lp_token.balanceOf(ve_nft.address) == initial_contract_balance + LP_AMOUNT
    
    # Check original vePower
    _, original_ve_power = ve_nft.getLockInfo(token_id)
    
    # Extend the lock to max duration
    tx2 = ve_nft.extendLock(token_id, HALF_LOCK, {'from': accounts[0]})
    new_token_id = tx2.return_value
    
    # Verify LP tokens are still in the contract (no change in balances during extension)
    assert lp_token.balanceOf(accounts[0]) == initial_user_balance - LP_AMOUNT
    assert lp_token.balanceOf(ve_nft.address) == initial_contract_balance + LP_AMOUNT
    
    # Check new lock information and vePower
    new_lock_info, new_ve_power = ve_nft.getLockInfo(new_token_id)
    assert new_lock_info[0] == LP_AMOUNT
    assert new_lock_info[3] == MAX_LOCK
    assert new_ve_power == LP_AMOUNT  # Now it should be full amount (vePower = amount)
    
    # Check that old token no longer exists (should raise an exception)
    try:
        ve_nft.getLockInfo(token_id)
        assert False, "Should have failed - token should not exist"
    except exceptions.VirtualMachineError:
        # This is expected - token doesn't exist anymore
        pass


def test_vePower_decay(setup, accounts):
    """Test that vePower decays linearly over time"""
    lp_token, ve_nft = setup
    
    # Create a lock for max duration (2 years)
    tx = ve_nft.createLock(LP_AMOUNT, MAX_LOCK, {'from': accounts[0]})
    token_id = tx.return_value
    
    # Check initial vePower
    _, initial_ve_power = ve_nft.getLockInfo(token_id)
    assert initial_ve_power == LP_AMOUNT
    
    # Move time forward 25% of the lock
    chain.sleep(MAX_LOCK // 4)
    chain.mine()
    
    # Check vePower after 25% time passed (should be about 75% of initial)
    _, ve_power_after_25_percent = ve_nft.getLockInfo(token_id)
    # Allow a small margin of error for block timestamp variations
    assert ve_power_after_25_percent < initial_ve_power
    assert ve_power_after_25_percent > (initial_ve_power * 70) // 100  # Should be roughly 75%
    
    # Move time to 50% of the lock
    chain.sleep(MAX_LOCK // 4)
    chain.mine()
    
    # Check vePower after 50% time passed (should be about 50% of initial)
    _, ve_power_after_50_percent = ve_nft.getLockInfo(token_id)
    assert ve_power_after_50_percent < ve_power_after_25_percent
    assert ve_power_after_50_percent > (initial_ve_power * 45) // 100  # Should be roughly 50%
    
    # Move time to complete lock duration
    chain.sleep(MAX_LOCK // 2)
    chain.mine()
    
    # Check vePower after full time (should be 0)
    _, ve_power_after_full_time = ve_nft.getLockInfo(token_id)
    assert ve_power_after_full_time == 0


def test_merge_locks_equal_amounts(setup, accounts):
    """Test merging two locks with equal amounts but different durations,
    ensuring proper LP token accounting"""
    lp_token, ve_nft = setup
    
    # Track initial balances
    initial_user_balance = lp_token.balanceOf(accounts[0])
    initial_contract_balance = lp_token.balanceOf(ve_nft.address)
    
    # Create first lock with max duration
    tx1 = ve_nft.createLock(LP_AMOUNT, MAX_LOCK, {'from': accounts[0]})
    token_id1 = tx1.return_value
    
    # Create second lock with half duration
    tx2 = ve_nft.createLock(LP_AMOUNT, HALF_LOCK, {'from': accounts[0]})
    token_id2 = tx2.return_value
    
    # Verify LP tokens transferred for both locks
    assert lp_token.balanceOf(accounts[0]) == initial_user_balance - (LP_AMOUNT * 2)
    assert lp_token.balanceOf(ve_nft.address) == initial_contract_balance + (LP_AMOUNT * 2)
    
    # Merge the locks
    tx3 = ve_nft.mergeLocks(token_id1, token_id2, {'from': accounts[0]})
    merged_token_id = tx3.return_value
    
    # Verify LP token balances remain the same after merge
    assert lp_token.balanceOf(accounts[0]) == initial_user_balance - (LP_AMOUNT * 2)
    assert lp_token.balanceOf(ve_nft.address) == initial_contract_balance + (LP_AMOUNT * 2)
    
    # Check merged lock information
    merged_lock, merged_ve_power = ve_nft.getLockInfo(merged_token_id)
    
    # Amount should be sum of both locks
    assert merged_lock[0] == LP_AMOUNT * 2
    
    # VePower should be weighted average: 
    # (LP_AMOUNT * 1.0 + LP_AMOUNT * 0.5) / (LP_AMOUNT * 2) = 0.75
    # So merged vePower should be approximately 0.75 * LP_AMOUNT * 2 = 1.5 * LP_AMOUNT
    expected_ve_power = (LP_AMOUNT * 3) // 2  # 1.5 * LP_AMOUNT
    # Allow some margin due to block timestamp variations
    assert merged_ve_power >= expected_ve_power * 95 // 100
    assert merged_ve_power <= expected_ve_power * 105 // 100
    
    # Duration should correspond to the vePower ratio
    expected_duration = (MAX_LOCK * 3) // 4  # 75% of MAX_LOCK
    assert merged_lock[3] >= expected_duration * 95 // 100
    assert merged_lock[3] <= expected_duration * 105 // 100
    
    # Verify original NFTs are burned by checking ownership
    try:
        ve_nft.getLockInfo(token_id1)
        assert False, "Should have failed - original token1 should be burned"
    except exceptions.VirtualMachineError:
        pass
        
    try:
        ve_nft.getLockInfo(token_id2)
        assert False, "Should have failed - original token2 should be burned"
    except exceptions.VirtualMachineError:
        pass


def test_merge_locks_unequal_amounts(setup, accounts):
    """Test merging two locks with unequal amounts and verify correct LP token accounting"""
    lp_token, ve_nft = setup
    
    # Track initial balances
    initial_user_balance = lp_token.balanceOf(accounts[0])
    initial_contract_balance = lp_token.balanceOf(ve_nft.address)
    
    # Create first lock with max duration and larger amount
    tx1 = ve_nft.createLock(LP_AMOUNT * 2, MAX_LOCK, {'from': accounts[0]})
    token_id1 = tx1.return_value
    
    # Create second lock with half duration and smaller amount
    tx2 = ve_nft.createLock(LP_AMOUNT, HALF_LOCK, {'from': accounts[0]})
    token_id2 = tx2.return_value
    
    # Verify LP tokens transferred for both locks
    assert lp_token.balanceOf(accounts[0]) == initial_user_balance - (LP_AMOUNT * 3)
    assert lp_token.balanceOf(ve_nft.address) == initial_contract_balance + (LP_AMOUNT * 3)
    
    # Merge the locks
    tx3 = ve_nft.mergeLocks(token_id1, token_id2, {'from': accounts[0]})
    merged_token_id = tx3.return_value
    
    # Verify LP token balances remain the same after merge
    assert lp_token.balanceOf(accounts[0]) == initial_user_balance - (LP_AMOUNT * 3)
    assert lp_token.balanceOf(ve_nft.address) == initial_contract_balance + (LP_AMOUNT * 3)
    
    # Check merged lock information
    merged_lock, merged_ve_power = ve_nft.getLockInfo(merged_token_id)
    
    # Amount should be sum of both locks
    assert merged_lock[0] == LP_AMOUNT * 3
    
    # VePower should be weighted average:
    # (LP_AMOUNT*2 * 1.0 + LP_AMOUNT * 0.5) / (LP_AMOUNT*3) = 5/6 ≈ 0.833
    # So merged vePower should be approximately 0.833 * LP_AMOUNT * 3 = 2.5 * LP_AMOUNT
    expected_ve_power = (LP_AMOUNT * 5) // 2  # 2.5 * LP_AMOUNT
    # Allow some margin due to block timestamp variations
    assert merged_ve_power >= expected_ve_power * 95 // 100
    assert merged_ve_power <= expected_ve_power * 105 // 100
    
    # Verify original NFTs are burned by checking they no longer exist
    try:
        ve_nft.getLockInfo(token_id1)
        assert False, "Should have failed - original token1 should be burned"
    except exceptions.VirtualMachineError:
        pass
        
    try:
        ve_nft.getLockInfo(token_id2)
        assert False, "Should have failed - original token2 should be burned"
    except exceptions.VirtualMachineError:
        pass


def test_withdraw_after_expiry(setup, accounts):
    """Test withdrawing locked LP tokens after lock has expired, 
    ensuring LP tokens are returned to the user"""
    lp_token, ve_nft = setup
    
    # Track initial balances
    initial_user_balance = lp_token.balanceOf(accounts[0])
    initial_contract_balance = lp_token.balanceOf(ve_nft.address)
    
    # Create a short lock (1 day)
    tx = ve_nft.createLock(LP_AMOUNT, ONE_DAY, {'from': accounts[0]})
    token_id = tx.return_value
    
    # Verify LP tokens were transferred to contract
    assert lp_token.balanceOf(accounts[0]) == initial_user_balance - LP_AMOUNT
    assert lp_token.balanceOf(ve_nft.address) == initial_contract_balance + LP_AMOUNT
    
    # Try to withdraw before lock expires - should fail
    try:
        ve_nft.withdraw(token_id, {'from': accounts[0]})
        assert False, "Should have failed - lock period not ended"
    except exceptions.VirtualMachineError as e:
        # This is expected
        assert "Lock period not ended" in str(e)
    
    # Move time forward past lock expiry
    chain.sleep(ONE_DAY + 10)
    chain.mine()
    
    # Withdraw LP tokens
    ve_nft.withdraw(token_id, {'from': accounts[0]})
    
    # Check LP tokens were returned to user
    assert lp_token.balanceOf(accounts[0]) == initial_user_balance
    assert lp_token.balanceOf(ve_nft.address) == initial_contract_balance
    
    # Check that NFT was burned
    try:
        ve_nft.getLockInfo(token_id)
        assert False, "Should have failed - token should not exist after withdraw"
    except exceptions.VirtualMachineError:
        # This is expected - token doesn't exist anymore
        pass


def test_preview_create_lock(setup, accounts):
    """Test the preview function for creating locks and verify it matches actual results"""
    lp_token, ve_nft = setup
    
    # Preview vePower for a max lock
    predicted_ve_power = ve_nft.previewCreateLock(LP_AMOUNT, MAX_LOCK)
    
    # Actually create the lock
    tx = ve_nft.createLock(LP_AMOUNT, MAX_LOCK, {'from': accounts[0]})
    token_id = tx.return_value
    
    # Get actual vePower
    _, actual_ve_power = ve_nft.getLockInfo(token_id)
    
    # Verify prediction matches result
    assert predicted_ve_power == actual_ve_power


def test_preview_extend_lock(setup, accounts):
    """Test the preview function for extending locks and verify it matches actual results"""
    lp_token, ve_nft = setup
    
    # Create a lock for half duration
    tx = ve_nft.createLock(LP_AMOUNT, HALF_LOCK, {'from': accounts[0]})
    token_id = tx.return_value
    
    # Preview extending to max lock
    predicted_ve_power = ve_nft.previewExtendLock(token_id, HALF_LOCK)
    
    # Actually extend the lock
    tx2 = ve_nft.extendLock(token_id, HALF_LOCK, {'from': accounts[0]})
    new_token_id = tx2.return_value
    
    # Get actual vePower
    _, actual_ve_power = ve_nft.getLockInfo(new_token_id)
    
    # Verify prediction matches result (allow small margin due to time passed during test)
    assert predicted_ve_power >= actual_ve_power * 99 // 100
    assert predicted_ve_power <= actual_ve_power * 101 // 100


def test_preview_merge_locks(setup, accounts):
    """Test the preview function for merging locks and verify it matches actual results"""
    lp_token, ve_nft = setup
    
    # Create two different locks
    tx1 = ve_nft.createLock(LP_AMOUNT, MAX_LOCK, {'from': accounts[0]})
    token_id1 = tx1.return_value
    
    tx2 = ve_nft.createLock(LP_AMOUNT, HALF_LOCK, {'from': accounts[0]})
    token_id2 = tx2.return_value
    
    # Preview merge
    predicted_ve_power, predicted_duration, predicted_amount = ve_nft.previewMergeLocks(token_id1, token_id2)
    
    # Actually merge
    tx3 = ve_nft.mergeLocks(token_id1, token_id2, {'from': accounts[0]})
    merged_token_id = tx3.return_value
    
    # Get actual values
    merged_lock, actual_ve_power = ve_nft.getLockInfo(merged_token_id)
    
    # Verify predictions match results
    assert predicted_amount == merged_lock[0]
    
    # Allow small margin due to time passed during test
    assert predicted_ve_power >= actual_ve_power * 99 // 100
    assert predicted_ve_power <= actual_ve_power * 101 // 100
    
    assert predicted_duration >= merged_lock[3] * 99 // 100
    assert predicted_duration <= merged_lock[3] * 101 // 100


def test_get_total_ve_power_for_owner(setup, accounts):
    """Test the function to get total vePower for an owner with multiple NFTs"""
    lp_token, ve_nft = setup
    
    # Create three locks with different durations for the same user
    tx1 = ve_nft.createLock(LP_AMOUNT, MAX_LOCK, {'from': accounts[0]})
    token_id1 = tx1.return_value
    
    tx2 = ve_nft.createLock(LP_AMOUNT, HALF_LOCK, {'from': accounts[0]})
    token_id2 = tx2.return_value
    
    tx3 = ve_nft.createLock(LP_AMOUNT, MAX_LOCK // 4, {'from': accounts[0]})
    token_id3 = tx3.return_value
    
    # Get individual vePowers
    _, ve_power1 = ve_nft.getLockInfo(token_id1)
    _, ve_power2 = ve_nft.getLockInfo(token_id2)
    _, ve_power3 = ve_nft.getLockInfo(token_id3)
    
    # Calculate expected total
    expected_total = ve_power1 + ve_power2 + ve_power3
    
    # Get actual total vePower
    actual_total = ve_nft.getTotalVePowerForOwner(accounts[0])
    
    # Verify they match
    assert actual_total == expected_total


def test_get_all_user_nfts(setup, accounts):
    """Test the function to get all NFTs owned by a user with full metadata"""
    lp_token, ve_nft = setup
    
    # Create two locks for the same user
    tx1 = ve_nft.createLock(LP_AMOUNT, MAX_LOCK, {'from': accounts[0]})
    token_id1 = tx1.return_value
    
    tx2 = ve_nft.createLock(SMALL_LP_AMOUNT, HALF_LOCK, {'from': accounts[0]})
    token_id2 = tx2.return_value
    
    # Get all NFTs for the user
    token_ids, lock_infos, ve_powers = ve_nft.getAllUserNFTs(accounts[0])
    
    # Check that we got the right number of NFTs
    assert len(token_ids) == 2
    assert len(lock_infos) == 2
    assert len(ve_powers) == 2
    
    # Check that the token IDs match
    assert token_id1 in token_ids
    assert token_id2 in token_ids
    
    # Get the index of each token in the returned arrays
    idx1 = token_ids.index(token_id1)
    idx2 = token_ids.index(token_id2)
    
    # Check that the lock amounts match
    assert lock_infos[idx1][0] == LP_AMOUNT
    assert lock_infos[idx2][0] == SMALL_LP_AMOUNT
    
    # Check that the vePowers match what we'd get from getLockInfo
    _, expected_ve_power1 = ve_nft.getLockInfo(token_id1)
    _, expected_ve_power2 = ve_nft.getLockInfo(token_id2)
    
    assert ve_powers[idx1] == expected_ve_power1
    assert ve_powers[idx2] == expected_ve_power2


def test_tokens_of_owner(setup, accounts):
    """Test the function to get all token IDs owned by a user"""
    lp_token, ve_nft = setup
    
    # Initially user should have no tokens
    tokens = ve_nft.getTokensOfOwner(accounts[0])
    assert len(tokens) == 0
    
    # Create some tokens for the user
    tx1 = ve_nft.createLock(LP_AMOUNT, MAX_LOCK, {'from': accounts[0]})
    token_id1 = tx1.return_value
    
    tx2 = ve_nft.createLock(LP_AMOUNT, HALF_LOCK, {'from': accounts[0]})
    token_id2 = tx2.return_value
    
    # Check user now has these tokens
    tokens = ve_nft.getTokensOfOwner(accounts[0])
    assert len(tokens) == 2
    assert token_id1 in tokens
    assert token_id2 in tokens
    
    # Create a token for another user
    tx3 = ve_nft.createLock(LP_AMOUNT, MAX_LOCK, {'from': accounts[1]})
    token_id3 = tx3.return_value
    
    # Check first user's tokens are unchanged
    tokens = ve_nft.getTokensOfOwner(accounts[0])
    assert len(tokens) == 2
    assert token_id1 in tokens
    assert token_id2 in tokens
    
    # Check second user has their token
    tokens = ve_nft.getTokensOfOwner(accounts[1])
    assert len(tokens) == 1
    assert token_id3 in tokens
def test_token_uri_metadata(setup, accounts):
    """Test that tokenURI returns correctly formatted metadata with accurate values"""
    import base64
    import json
    
    lp_token, ve_nft = setup
    
    # Create a lock for half duration (1 year)
    tx = ve_nft.createLock(LP_AMOUNT, HALF_LOCK, {'from': accounts[0]})
    token_id = tx.return_value
    
    # Get the token URI
    uri = ve_nft.tokenURI(token_id)
    
    # Verify the URI starts with the correct prefix
    assert uri.startswith('data:application/json;base64,'), "URI doesn't start with correct prefix"
    
    # Extract base64 part
    base64_part = uri.replace('data:application/json;base64,', '')
    
    # Decode base64
    decoded_bytes = base64.b64decode(base64_part)
    decoded_json = decoded_bytes.decode('utf-8')
    
    # Parse JSON
    metadata = json.loads(decoded_json)
    
    # Verify the metadata structure and values
    assert "name" in metadata, "Metadata missing name field"
    assert f"veNFT #{token_id}" == metadata["name"], "Incorrect NFT name"
    
    assert "description" in metadata, "Metadata missing description field"
    assert "Vote Escrowed NFT for locked LP tokens" == metadata["description"], "Incorrect description"
    
    assert "attributes" in metadata, "Metadata missing attributes"
    attributes = {attr["trait_type"]: attr["value"] for attr in metadata["attributes"]}
    
    # Check LP Amount
    assert "LP Amount" in attributes, "Metadata missing LP Amount attribute"
    assert str(LP_AMOUNT) == attributes["LP Amount"], "LP Amount doesn't match"
    
    # Check Lock Duration
    assert "Lock Duration" in attributes, "Metadata missing Lock Duration attribute"
    expected_duration_days = HALF_LOCK // ONE_DAY
    assert f"{expected_duration_days} days" == attributes["Lock Duration"], "Lock Duration doesn't match"
    
    # Check Current VePower
    assert "Current VePower" in attributes, "Metadata missing Current VePower attribute"
    # For half duration, vePower should be approximately half of LP_AMOUNT
    # Note: The % character is in the output format even though it's not a percentage
    ve_power_str = attributes["Current VePower"].replace("%", "")
    ve_power = int(ve_power_str)
    # Allow for some minor deviation due to block timing
    assert ve_power >= (LP_AMOUNT // 2) * 95 // 100, "VePower too low"
    assert ve_power <= (LP_AMOUNT // 2) * 105 // 100, "VePower too high"
    
    # Check Remaining Time
    assert "Remaining Time" in attributes, "Metadata missing Remaining Time attribute"
    # Initially remaining time should match lock duration
    assert f"{expected_duration_days} days" == attributes["Remaining Time"], "Remaining Time doesn't match"
    
    # Check End Date exists (exact value depends on block.timestamp)
    assert any(key.startswith("End Date") for key in attributes.keys()), "Metadata missing End Date attribute"
    
    # Test after time passes
    chain.sleep(HALF_LOCK // 2)  # Sleep half of lock period
    chain.mine()
    
    # Get updated token URI
    updated_uri = ve_nft.tokenURI(token_id)
    updated_base64 = updated_uri.replace('data:application/json;base64,', '')
    updated_json = base64.b64decode(updated_base64).decode('utf-8')
    updated_metadata = json.loads(updated_json)
    updated_attributes = {attr["trait_type"]: attr["value"] for attr in updated_metadata["attributes"]}
    
    # Remaining time should be approximately half the original
    remaining_days = int(updated_attributes["Remaining Time"].split(" ")[0])
    assert remaining_days < expected_duration_days, "Remaining Time didn't decrease"
    assert remaining_days > 0, "Remaining Time shouldn't be zero yet"
    
    # VePower should have decreased to around 1/4 of LP_AMOUNT
    ve_power_str = updated_attributes["Current VePower"].replace("%", "")
    ve_power = int(ve_power_str)
    # Allow for some deviation due to block timing
    assert ve_power < (LP_AMOUNT // 2), "VePower didn't decrease"
    assert ve_power >= (LP_AMOUNT // 4) * 90 // 100, "VePower decreased too much"
    assert ve_power <= (LP_AMOUNT // 4) * 110 // 100, "VePower didn't decrease enough"