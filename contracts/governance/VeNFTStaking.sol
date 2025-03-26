// // SPDX-License-Identifier: MIT
// pragma solidity ^0.8.10;

// import "@openzeppelin/contracts/token/ERC721/IERC721.sol";
// import "@openzeppelin/contracts/token/ERC721/utils/ERC721Holder.sol";
// import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
// import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
// import "@openzeppelin/contracts/access/Ownable.sol";
// import "@openzeppelin/contracts/security/ReentrancyGuard.sol";
// import "@openzeppelin/contracts/utils/math/Math.sol";


// // Interface for the veNFT contract
// interface IVeNFT is IERC721 {
//     struct LockInfo {
//         uint256 amount;
//         uint256 startTime;
//         uint256 endTime;
//         uint256 lockDuration;
//     }
    
//     function getCurrentVePower(uint256 tokenId) external view returns (uint256);
//     function getLockInfo(uint256 tokenId) external view returns (LockInfo memory lockInfo, uint256 currentVePower);
// }

// /**
//  * @title OptimizedMultiRewardVeNFTStaking
//  * @dev Staking contract for veNFT tokens with optimized reward distribution based on time-weighted average VePower
//  * Uses a linear equation model for efficient VePower tracking
//  */
// contract OptimizedMultiRewardVeNFTStaking is ERC721Holder, Ownable, ReentrancyGuard {
//     using SafeERC20 for IERC20;

    

//     // Constants
//     uint256 public constant MAX_LOCK_DURATION = 730 days; // Must match VeNFT contract
//     uint256 public constant PRECISION = 1e18;

//     // veNFT contract
//     IVeNFT public veNFT;

//     // Staked Position Info
//     struct StakedPosition {
//         uint256 tokenId;
//         uint256 vePowerAtStakeTime;
//         uint256 stakeTime;
//         uint256 endTime;
//         uint256 lpAmount;
//     }

//     // Reward Token Info
//     struct RewardTokenInfo {
//         IERC20 token;
//         uint256 rewardRate;               // Rewards per second
//         uint256 lastUpdateTime;           // Last time rewards were calculated
//         uint256 accRewardPerShare;        // Accumulated rewards per share (scaled by PRECISION)
//         uint256 remainingRewards;         // Remaining rewards to distribute
//         bool isActive;                    // Whether this reward token is active
//     }

//     // User Info for a specific reward token
//     struct UserRewardInfo {
//         uint256 rewardDebt;               // Reward debt for this token
//         uint256 pendingRewards;           // Unclaimed rewards for this token
//         uint256 userLastUpdateTime;       // Last time user rewards were updated for this token
//     }

//     // User Info
//     struct UserInfo {
//         StakedPosition[] stakedPositions;
//         uint256 lastTotalVePower;         // Total user VePower at last update
//         uint256 lastUpdateTime;           // Last time user data was updated
//         mapping(address => UserRewardInfo) tokenRewardInfo;  // User rewards per token
//     }

//     // Global Linear VePower Model
//     struct LinearVePowerModel {
//         uint256 slopeSum;           // Sum of all slopes (∑b_i): lpAmount/MAX_LOCK_DURATION
//         uint256 offsetSum;          // Sum of all offsets (∑a_i): lpAmount*endTime/MAX_LOCK_DURATION
//         uint256 lastUpdateTime;     // Last time the model was updated
//     }

//     // Global state variables
//     mapping(address => RewardTokenInfo) public rewardTokens;
//     address[] public rewardTokenAddresses;
    
//     // Global VePower tracking
//     uint256 public totalVePowerStaked;     // Total VePower of all staked NFTs
//     uint256 public lastGlobalUpdateTime;   // Last time global VePower was updated
//     LinearVePowerModel public globalVePowerModel;
    
//     // User state
//     mapping(address => UserInfo) public userInfo;
    
//     // tokenId => staker address mapping for quick lookup
//     mapping(uint256 => address) public tokenOwners;
    
//     // Events
//     event Staked(address indexed user, uint256 tokenId, uint256 vePower);
//     event Unstaked(address indexed user, uint256 tokenId);
//     event RewardClaimed(address indexed user, address indexed token, uint256 amount);
//     event RewardTokenAdded(address indexed token, uint256 rewardRate);
//     event RewardTokenRemoved(address indexed token);
//     event RewardRateUpdated(address indexed token, uint256 newRate);
//     event RewardsAdded(address indexed token, uint256 amount);
//     event VePowerUpdated(address indexed user, uint256 newTotalVePower);

//     /**
//      * @dev Constructor
//      * @param _veNFT Address of the veNFT contract
//      */
//     constructor(address _veNFT) {
//         require(_veNFT != address(0), "Invalid veNFT address");
//         veNFT = IVeNFT(_veNFT);
//         lastGlobalUpdateTime = block.timestamp;
//         globalVePowerModel.lastUpdateTime = block.timestamp;
//     }

//     /**
//      * @dev Add a new reward token
//      * @param tokenAddress Address of the reward token
//      * @param initialRewardRate Initial reward rate per second
//      */
//     function addRewardToken(address tokenAddress, uint256 initialRewardRate) external onlyOwner {
//         require(tokenAddress != address(0), "Invalid token address");
//         require(!rewardTokens[tokenAddress].isActive, "Token already added");
        
//         // Add new reward token
//         rewardTokens[tokenAddress] = RewardTokenInfo({
//             token: IERC20(tokenAddress),
//             rewardRate: initialRewardRate,
//             lastUpdateTime: block.timestamp,
//             accRewardPerShare: 0,
//             remainingRewards: 0,
//             isActive: true
//         });
        
//         rewardTokenAddresses.push(tokenAddress);
        
//         emit RewardTokenAdded(tokenAddress, initialRewardRate);
//     }

//     /**
//      * @dev Remove a reward token
//      * @param tokenAddress Address of the reward token to remove
//      */
//     function removeRewardToken(address tokenAddress) external onlyOwner {
//         require(rewardTokens[tokenAddress].isActive, "Token not active");
        
//         // Update rewards before removing the token
//         updateRewardState(tokenAddress);
        
//         // Mark as inactive
//         rewardTokens[tokenAddress].isActive = false;
        
//         // Remove from active token list
//         for (uint256 i = 0; i < rewardTokenAddresses.length; i++) {
//             if (rewardTokenAddresses[i] == tokenAddress) {
//                 rewardTokenAddresses[i] = rewardTokenAddresses[rewardTokenAddresses.length - 1];
//                 rewardTokenAddresses.pop();
//                 break;
//             }
//         }
        
//         emit RewardTokenRemoved(tokenAddress);
//     }

//     /**
//      * @dev Calculate the current VePower of a staked position
//      * @param position The staked position
//      * @return The current VePower of the position
//      */
//     function getCurrentPositionVePower(StakedPosition memory position) public view returns (uint256) {
//         // If position has expired, VePower is 0
//         if (block.timestamp >= position.endTime) {
//             return 0;
//         }
        
//         // Calculate remaining time
//         uint256 remainingTime = position.endTime - block.timestamp;
        
//         // VePower = LP amount * (remainingTime / MAX_LOCK_DURATION)
//         return (position.lpAmount * remainingTime) / MAX_LOCK_DURATION;
//     }

//     /**
//      * @dev Calculate the linear equation parameters for a position
//      * @param position The staked position
//      * @return a Offset parameter (a = lpAmount * endTime / MAX_LOCK_DURATION)
//      * @return b Slope parameter (b = lpAmount / MAX_LOCK_DURATION)
//      */
//     function getPositionLinearParameters(StakedPosition memory position) public pure returns (uint256 a, uint256 b) {
//         a = (position.lpAmount * position.endTime) / MAX_LOCK_DURATION;
//         b = position.lpAmount / MAX_LOCK_DURATION;
//         return (a, b);
//     }

//     /**
//      * @dev Calculate the average VePower over a period
//      * @param startVePower VePower at the start of the period
//      * @param endVePower VePower at the end of the period
//      * @return Average VePower over the period
//      */
//     function calculateAverageVePower(uint256 startVePower, uint256 endVePower) public pure returns (uint256) {
//         // For linear decay, average is the midpoint
//         return (startVePower + endVePower) / 2;
//     }

//     /**
//      * @dev Calculate the current total VePower of a user
//      * @param user The user address
//      * @return The current total VePower of the user
//      */
//     function calculateCurrentUserVePower(address user) public view returns (uint256) {
//         UserInfo storage userData = userInfo[user];
//         uint256 currentTotalVePower = 0;
        
//         for (uint256 i = 0; i < userData.stakedPositions.length; i++) {
//             currentTotalVePower += getCurrentPositionVePower(userData.stakedPositions[i]);
//         }
        
//         return currentTotalVePower;
//     }

//     /**
//      * @dev Calculate the average VePower of a user over a period
//      * @param user The user address
//      * @param startTime Start of the period
//      * @param endTime End of the period
//      * @return The time-weighted average VePower of the user over the period
//      */
//     function calculateUserAverageVePower(
//         address user, 
//         uint256 startTime, 
//         uint256 endTime
//     ) public view returns (uint256) {
//         if (startTime >= endTime) return 0;
        
//         // Calculate VePower at start time
//         uint256 startVePower = getUserVePowerAt(user, startTime);
        
//         // Calculate VePower at end time
//         uint256 endVePower = getUserVePowerAt(user, endTime);
        
//         // Return average
//         return calculateAverageVePower(startVePower, endVePower);
//     }
    
//     /**
//      * @dev Calculate a user's VePower at a specific timestamp
//      * @param user The user address
//      * @param timestamp The timestamp to calculate VePower for
//      * @return The user's VePower at the specified timestamp
//      */
//     function getUserVePowerAt(address user, uint256 timestamp) public view returns (uint256) {
//         UserInfo storage userData = userInfo[user];
//         uint256 totalVePower = 0;
        
//         for (uint256 i = 0; i < userData.stakedPositions.length; i++) {
//             StakedPosition memory position = userData.stakedPositions[i];
            
//             // Skip if position was staked after the timestamp or already expired
//             if (position.stakeTime > timestamp || timestamp >= position.endTime) {
//                 continue;
//             }
            
//             // Calculate VePower at the specified timestamp
//             uint256 remainingTime = position.endTime - timestamp;
//             uint256 positionVePower = (position.lpAmount * remainingTime) / MAX_LOCK_DURATION;
            
//             totalVePower += positionVePower;
//         }
        
//         return totalVePower;
//     }

//     /**
//      * @dev Calculate the current global VePower using the linear equation model
//      * @return Current total VePower across all staked positions
//      */
//     function calculateCurrentTotalVePower() public view returns (uint256) {
//         // Use the linear equation: TotalVePower(t) = offsetSum - slopeSum * t
//         if (globalVePowerModel.offsetSum <= globalVePowerModel.slopeSum * block.timestamp) {
//             return 0; // Avoid underflow if all positions have expired
//         }
        
//         return globalVePowerModel.offsetSum - globalVePowerModel.slopeSum * block.timestamp;
//     }

//     /**
//      * @dev Update the global VePower state
//      */
//     function updateGlobalVePower() public {
//         if (block.timestamp <= lastGlobalUpdateTime) {
//             return;
//         }
        
//         // Update the cached value of totalVePowerStaked
//         totalVePowerStaked = calculateCurrentTotalVePower();
//         lastGlobalUpdateTime = block.timestamp;
//     }

//     /**
//      * @dev Estimate total VePower at a given timestamp
//      * @param timestamp Timestamp to calculate VePower for
//      * @return Total VePower estimate
//      */
//     function getTotalVePowerAt(uint256 timestamp) public view returns (uint256) {
//         // Use the linear equation model with the specified timestamp
//         if (globalVePowerModel.offsetSum <= globalVePowerModel.slopeSum * timestamp) {
//             return 0;
//         }
        
//         return globalVePowerModel.offsetSum - globalVePowerModel.slopeSum * timestamp;
//     }

//     /**
//      * @dev Calculate time-weighted average VePower over a period
//      * @param startTime Start time
//      * @param endTime End time
//      * @return Global time-weighted average VePower
//      */
//     function calculateGlobalAverageVePower(uint256 startTime, uint256 endTime) public view returns (uint256) {
//         uint256 startVePower = getTotalVePowerAt(startTime);
//         uint256 endVePower = getTotalVePowerAt(endTime);
        
//         return calculateAverageVePower(startVePower, endVePower);
//     }

//     /**
//      * @dev Update the global reward state for a specific token
//      * @param tokenAddress Address of the reward token
//      */
//     function updateRewardState(address tokenAddress) public {
//         RewardTokenInfo storage tokenInfo = rewardTokens[tokenAddress];
        
//         if (!tokenInfo.isActive || block.timestamp <= tokenInfo.lastUpdateTime) {
//             return;
//         }
        
//         // First update global VePower
//         updateGlobalVePower();
        
//         uint256 timeElapsed = block.timestamp - tokenInfo.lastUpdateTime;
        
//         if (totalVePowerStaked > 0 && timeElapsed > 0) {
//             // Calculate rewards for the period
//             uint256 rewards = Math.min(
//                 tokenInfo.rewardRate * timeElapsed,
//                 tokenInfo.remainingRewards
//             );
            
//             if (rewards > 0) {
//                 // Calculate the time-weighted average of total VePower during this period
//                 uint256 avgTotalVePower = calculateGlobalAverageVePower(
//                     tokenInfo.lastUpdateTime,
//                     block.timestamp
//                 );
                
//                 if (avgTotalVePower > 0) {
//                     tokenInfo.accRewardPerShare += (rewards * PRECISION) / avgTotalVePower;
//                     tokenInfo.remainingRewards -= rewards;
//                 }
//             }
//         }
        
//         tokenInfo.lastUpdateTime = block.timestamp;
//     }

//     /**
//      * @dev Update reward states for all active tokens
//      */
//     function updateAllRewardStates() public {
//         // Update global VePower
//         updateGlobalVePower();
        
//         // Update reward states for all tokens
//         for (uint256 i = 0; i < rewardTokenAddresses.length; i++) {
//             if (rewardTokens[rewardTokenAddresses[i]].isActive) {
//                 updateRewardState(rewardTokenAddresses[i]);
//             }
//         }
//     }

//     /**
//      * @dev Update a user's rewards for a specific token
//      * @param user User address
//      * @param tokenAddress Reward token address
//      */
//     function updateUserRewards(address user, address tokenAddress) internal {
//         RewardTokenInfo storage tokenInfo = rewardTokens[tokenAddress];
//         UserInfo storage userData = userInfo[user];
//         UserRewardInfo storage userRewardInfo = userData.tokenRewardInfo[tokenAddress];
        
//         // First update the global reward state
//         updateRewardState(tokenAddress);
        
//         if (userData.stakedPositions.length > 0) {
//             // Calculate time periods
//             uint256 startTime = Math.max(userRewardInfo.userLastUpdateTime, tokenInfo.lastUpdateTime - 1);
//             uint256 endTime = block.timestamp;
            
//             if (startTime < endTime) {
//                 // Calculate user's average VePower over this period
//                 uint256 userAvgVePower = calculateUserAverageVePower(user, startTime, endTime);
                
//                 // Calculate rewards based on average VePower and accrued reward per share
//                 if (userAvgVePower > 0) {
//                     uint256 accReward = (userAvgVePower * 
//                         (tokenInfo.accRewardPerShare - userRewardInfo.rewardDebt)) / PRECISION;
                    
//                     // Add to pending rewards
//                     userRewardInfo.pendingRewards += accReward;
//                 }
//             }
//         }
        
//         // Update user reward state
//         userRewardInfo.rewardDebt = tokenInfo.accRewardPerShare;
//         userRewardInfo.userLastUpdateTime = block.timestamp;
//     }

//     /**
//      * @dev Update a user's rewards for all active tokens
//      * @param user User address
//      */
//     function updateUserRewardsForAllTokens(address user) internal {
//         for (uint256 i = 0; i < rewardTokenAddresses.length; i++) {
//             address tokenAddress = rewardTokenAddresses[i];
//             if (rewardTokens[tokenAddress].isActive) {
//                 updateUserRewards(user, tokenAddress);
//             }
//         }
//     }

//     /**
//      * @dev Update global VePower state when a new position is staked
//      */
//     function _updateGlobalVePowerOnStake(StakedPosition memory position) internal {
//         // Calculate the parameters of the linear equation for this position
//         (uint256 a, uint256 b) = getPositionLinearParameters(position);
        
//         // Add to the global sums
//         globalVePowerModel.offsetSum += a;
//         globalVePowerModel.slopeSum += b;
//         globalVePowerModel.lastUpdateTime = block.timestamp;
        
//         // Update cached totalVePowerStaked
//         totalVePowerStaked = calculateCurrentTotalVePower();
//     }

//     /**
//      * @dev Update global VePower state when a position is unstaked
//      */
//     function _updateGlobalVePowerOnUnstake(StakedPosition memory position) internal {
//         // Calculate the parameters of the linear equation for this position
//         (uint256 a, uint256 b) = getPositionLinearParameters(position);
        
//         // Subtract from the global sums with underflow protection
//         if (globalVePowerModel.offsetSum >= a) {
//             globalVePowerModel.offsetSum -= a;
//         } else {
//             globalVePowerModel.offsetSum = 0;
//         }
        
//         if (globalVePowerModel.slopeSum >= b) {
//             globalVePowerModel.slopeSum -= b;
//         } else {
//             globalVePowerModel.slopeSum = 0;
//         }
        
//         globalVePowerModel.lastUpdateTime = block.timestamp;
        
//         // Update cached totalVePowerStaked
//         totalVePowerStaked = calculateCurrentTotalVePower();
//     }

//     /**
//      * @dev Stake a veNFT
//      * @param tokenId ID of the veNFT to stake
//      */
//     function stake(uint256 tokenId) external nonReentrant {
//         // Update all reward states first
//         updateAllRewardStates();
        
//         // Update user rewards
//         updateUserRewardsForAllTokens(msg.sender);
        
//         // Get token info from veNFT contract
//         (IVeNFT.LockInfo memory lockInfo, uint256 vePower) = veNFT.getLockInfo(tokenId);
        
//         require(vePower > 0, "Token has no voting power or has expired");
        
//         // Transfer token to this contract
//         veNFT.safeTransferFrom(msg.sender, address(this), tokenId);
        
//         // Map token to owner
//         tokenOwners[tokenId] = msg.sender;
        
//         // Create staked position
//         StakedPosition memory position = StakedPosition({
//             tokenId: tokenId,
//             vePowerAtStakeTime: vePower,
//             stakeTime: block.timestamp,
//             endTime: lockInfo.endTime,
//             lpAmount: lockInfo.amount
//         });
        
//         // Add to user's staked positions
//         userInfo[msg.sender].stakedPositions.push(position);
        
//         // Update user's VePower
//         UserInfo storage userData = userInfo[msg.sender];
//         userData.lastTotalVePower = calculateCurrentUserVePower(msg.sender);
//         userData.lastUpdateTime = block.timestamp;
        
//         // Update global VePower model
//         _updateGlobalVePowerOnStake(position);
        
//         emit Staked(msg.sender, tokenId, vePower);
//     }

//     /**
//      * @dev Unstake a veNFT
//      * @param tokenId ID of the veNFT to unstake
//      */
//     function unstake(uint256 tokenId) external nonReentrant {
//         require(tokenOwners[tokenId] == msg.sender, "Not token owner");
        
//         // Update all reward states
//         updateAllRewardStates();
        
//         // Update user rewards
//         updateUserRewardsForAllTokens(msg.sender);
        
//         // Find the token in user's staked positions
//         UserInfo storage userData = userInfo[msg.sender];
//         uint256 positionIndex = type(uint256).max;
        
//         for (uint256 i = 0; i < userData.stakedPositions.length; i++) {
//             if (userData.stakedPositions[i].tokenId == tokenId) {
//                 positionIndex = i;
//                 break;
//             }
//         }
        
//         require(positionIndex != type(uint256).max, "Token not found");
        
//         // Update global VePower model before removing position
//         _updateGlobalVePowerOnUnstake(userData.stakedPositions[positionIndex]);
        
//         // Remove position from array (swap with last element and pop)
//         userData.stakedPositions[positionIndex] = userData.stakedPositions[userData.stakedPositions.length - 1];
//         userData.stakedPositions.pop();
        
//         // Update user's VePower
//         userData.lastTotalVePower = calculateCurrentUserVePower(msg.sender);
//         userData.lastUpdateTime = block.timestamp;
        
//         // Remove token ownership mapping
//         delete tokenOwners[tokenId];
        
//         // Transfer veNFT back to user
//         veNFT.safeTransferFrom(address(this), msg.sender, tokenId);
        
//         emit Unstaked(msg.sender, tokenId);
//     }

//     /**
//      * @dev Claim rewards for a specific token
//      * @param tokenAddress Address of the reward token
//      */
//     function claimRewards(address tokenAddress) external nonReentrant {
//         // Update user rewards first
//         updateUserRewards(msg.sender, tokenAddress);
        
//         // Get pending rewards
//         UserRewardInfo storage userRewardInfo = userInfo[msg.sender].tokenRewardInfo[tokenAddress];
//         uint256 pendingRewards = userRewardInfo.pendingRewards;
        
//         require(pendingRewards > 0, "No rewards to claim");
        
//         // Reset pending rewards
//         userRewardInfo.pendingRewards = 0;
        
//         // Transfer rewards to user
//         RewardTokenInfo storage tokenInfo = rewardTokens[tokenAddress];
//         tokenInfo.token.safeTransfer(msg.sender, pendingRewards);
        
//         emit RewardClaimed(msg.sender, tokenAddress, pendingRewards);
//     }

//     /**
//      * @dev Claim rewards for all active tokens
//      */
//     function claimAllRewards() external nonReentrant {
//         // Update user rewards for all tokens
//         updateUserRewardsForAllTokens(msg.sender);
        
//         // Claim all pending rewards
//         for (uint256 i = 0; i < rewardTokenAddresses.length; i++) {
//             address tokenAddress = rewardTokenAddresses[i];
//             UserRewardInfo storage userRewardInfo = userInfo[msg.sender].tokenRewardInfo[tokenAddress];
            
//             uint256 pendingRewards = userRewardInfo.pendingRewards;
            
//             if (pendingRewards > 0) {
//                 // Reset pending rewards
//                 userRewardInfo.pendingRewards = 0;
                
//                 // Transfer rewards
//                 RewardTokenInfo storage tokenInfo = rewardTokens[tokenAddress];
//                 tokenInfo.token.safeTransfer(msg.sender, pendingRewards);
                
//                 emit RewardClaimed(msg.sender, tokenAddress, pendingRewards);
//             }
//         }
//     }

//     /**
//      * @dev Set the reward rate for a token
//      * @param tokenAddress Address of the reward token
//      * @param newRewardRate New reward rate per second
//      */
//     function setRewardRate(address tokenAddress, uint256 newRewardRate) external onlyOwner {
//         require(rewardTokens[tokenAddress].isActive, "Token not active");
        
//         // Update reward state with old rate before changing
//         updateRewardState(tokenAddress);
        
//         rewardTokens[tokenAddress].rewardRate = newRewardRate;
        
//         emit RewardRateUpdated(tokenAddress, newRewardRate);
//     }

//     /**
//      * @dev Add rewards for a token
//      * @param tokenAddress Address of the reward token
//      * @param amount Amount to add
//      */
//     function addRewards(address tokenAddress, uint256 amount) external {
//         require(rewardTokens[tokenAddress].isActive, "Token not active");
//         require(amount > 0, "Amount must be greater than 0");
        
//         // Update reward state before adding rewards
//         updateRewardState(tokenAddress);
        
//         // Transfer tokens from caller to contract
//         rewardTokens[tokenAddress].token.safeTransferFrom(msg.sender, address(this), amount);
        
//         // Add to remaining rewards
//         rewardTokens[tokenAddress].remainingRewards += amount;
        
//         emit RewardsAdded(tokenAddress, amount);
//     }

//     /**
//      * @dev Emergency recover ERC20 tokens
//      * @param tokenAddress Address of the token to recover
//      * @param amount Amount to recover
//      */
//     function recoverERC20(address tokenAddress, uint256 amount) external onlyOwner {
//         require(!rewardTokens[tokenAddress].isActive, "Cannot recover active reward token");
        
//         IERC20(tokenAddress).safeTransfer(owner(), amount);
//     }

//     /**
//      * @dev Get all staked positions for a user
//      * @param user User address
//      * @return Array of staked positions
//      */
//     function getStakedPositions(address user) external view returns (StakedPosition[] memory) {
//         return userInfo[user].stakedPositions;
//     }

//     /**
//      * @dev Get pending rewards for a specific token
//      * @param user User address
//      * @param tokenAddress Reward token address
//      * @return Pending rewards amount
//      */
//     function pendingRewards(address user, address tokenAddress) external view returns (uint256) {
//         UserInfo storage userData = userInfo[user];
//         RewardTokenInfo storage tokenInfo = rewardTokens[tokenAddress];
//         UserRewardInfo storage userRewardInfo = userData.tokenRewardInfo[tokenAddress];
        
//         uint256 pending = userRewardInfo.pendingRewards;
        
//         if (userData.stakedPositions.length == 0) {
//             return pending;
//         }
        
//         // Calculate hypothetical rewards since last update
//         uint256 startTime = Math.max(userRewardInfo.userLastUpdateTime, tokenInfo.lastUpdateTime);
        
//         if (block.timestamp > startTime) {
//             // Calculate current reward per share
//             uint256 curAccRewardPerShare = tokenInfo.accRewardPerShare;
            
//             if (totalVePowerStaked > 0 && block.timestamp > tokenInfo.lastUpdateTime && tokenInfo.isActive) {
//                 uint256 timeElapsed = block.timestamp - tokenInfo.lastUpdateTime;
//                 uint256 rewards = Math.min(
//                     tokenInfo.rewardRate * timeElapsed,
//                     tokenInfo.remainingRewards
//                 );
                
//                 if (rewards > 0) {
//                     // Calculate average total VePower during this period
//                     uint256 avgTotalVePower = calculateGlobalAverageVePower(
//                         tokenInfo.lastUpdateTime,
//                         block.timestamp
//                     );
                    
//                     if (avgTotalVePower > 0) {
//                         curAccRewardPerShare += (rewards * PRECISION) / avgTotalVePower;
//                     }
//                 }
//             }
            
//             // Calculate user's average VePower over this period
//             uint256 userAvgVePower = calculateUserAverageVePower(user, startTime, block.timestamp);
            
//             // Calculate additional rewards
//             if (userAvgVePower > 0) {
//                 pending += (userAvgVePower * (curAccRewardPerShare - userRewardInfo.rewardDebt)) / PRECISION;
//             }
//         }
        
//         return pending;
//     }

//     /**
//      * @dev Get pending rewards for all active tokens
//      * @param user User address
//      * @return tokenAddresses Array of token addresses
//      * @return amounts Array of pending reward amounts
//      */
//     function getAllPendingRewards(address user) external view returns (
//         address[] memory tokenAddresses,
//         uint256[] memory amounts
//     ) {
//         tokenAddresses = new address[](rewardTokenAddresses.length);
//         amounts = new uint256[](rewardTokenAddresses.length);
        
//         for (uint256 i = 0; i < rewardTokenAddresses.length; i++) {
//             address tokenAddress = rewardTokenAddresses[i];
//             tokenAddresses[i] = tokenAddress;
            
//             UserInfo storage userData = userInfo[user];
//             RewardTokenInfo storage tokenInfo = rewardTokens[tokenAddress];
//             UserRewardInfo storage userRewardInfo = userData.tokenRewardInfo[tokenAddress];
            
//             uint256 pending = userRewardInfo.pendingRewards;
            
//             if (userData.stakedPositions.length > 0) {
//                 // Calculate hypothetical rewards since last update
//                 uint256 startTime = Math.max(userRewardInfo.userLastUpdateTime, tokenInfo.lastUpdateTime);
                
//                 if (block.timestamp > startTime) {
//                     // Calculate current reward per share
//                     uint256 curAccRewardPerShare = tokenInfo.accRewardPerShare;
                    
//                     if (totalVePowerStaked > 0 && block.timestamp > tokenInfo.lastUpdateTime && tokenInfo.isActive) {
//                         uint256 timeElapsed = block.timestamp - tokenInfo.lastUpdateTime;
//                         uint256 rewards = Math.min(
//                             tokenInfo.rewardRate * timeElapsed,
//                             tokenInfo.remainingRewards
//                         );
                        
//                         if (rewards > 0) {
//                             // Calculate average total VePower during this period
//                             uint256 avgTotalVePower = calculateGlobalAverageVePower(
//                                 tokenInfo.lastUpdateTime,
//                                 block.timestamp
//                             );
                            
//                             if (avgTotalVePower > 0) {
//                                 curAccRewardPerShare += (rewards * PRECISION) / avgTotalVePower;
//                             }
//                         }
//                     }
                    
//                     // Calculate user's average VePower over this period
//                     uint256 userAvgVePower = calculateUserAverageVePower(user, startTime, block.timestamp);
                    
//                     // Calculate additional rewards
//                     if (userAvgVePower > 0) {
//                         pending += (userAvgVePower * (curAccRewardPerShare - userRewardInfo.rewardDebt)) / PRECISION;
//                     }
//                 }
//             }
            
//             amounts[i] = pending;
//         }
        
//         return (tokenAddresses, amounts);
//     }

//     /**
//      * @dev Get active reward tokens
//      * @return List of active reward token addresses
//      */
//     function getActiveRewardTokens() external view returns (address[] memory) {
//         uint256 activeCount = 0;
        
//         // Count active tokens
//         for (uint256 i = 0; i < rewardTokenAddresses.length; i++) {
//             if (rewardTokens[rewardTokenAddresses[i]].isActive) {
//                 activeCount++;
//             }
//         }
        
//         // Create result array
//         address[] memory activeTokens = new address[](activeCount);
        
//         // Fill active tokens
//         uint256 index = 0;
//         for (uint256 i = 0; i < rewardTokenAddresses.length; i++) {
//             address tokenAddress = rewardTokenAddresses[i];
//             if (rewardTokens[tokenAddress].isActive) {
//                 activeTokens[index] = tokenAddress;
//                 index++;
//             }
//         }
        
//         return activeTokens;
//     }

//     /**
//      * @dev Calculates the total decay rate across all staked positions
//      * @return Total decay rate in VePower per second
//      */
//     function getTotalDecayRate() public view returns (uint256) {
//         // In our linear model, the slope sum represents the total decay rate
//         return globalVePowerModel.slopeSum;
//     }

//     /**
//      * @dev Updates user vePower data
//      * @param user User address to update
//      */
//     function updateUserVePower(address user) external {
//         UserInfo storage userData = userInfo[user];
        
//         // Update user rewards first
//         updateUserRewardsForAllTokens(user);
        
//         // Update user's VePower
//         userData.lastTotalVePower = calculateCurrentUserVePower(user);
//         userData.lastUpdateTime = block.timestamp;
        
//         emit VePowerUpdated(user, userData.lastTotalVePower);
//     }

//     /**
//      * @dev Get reward token info
//      * @param tokenAddress Reward token address
//      * @return Token info struct
//      */
//     function getRewardTokenInfo(address tokenAddress) external view returns (
//         uint256 rewardRate,
//         uint256 lastUpdateTime,
//         uint256 accRewardPerShare,
//         uint256 remainingRewards,
//         bool isActive
//     ) {
//         RewardTokenInfo storage tokenInfo = rewardTokens[tokenAddress];
//         return (
//             tokenInfo.rewardRate,
//             tokenInfo.lastUpdateTime,
//             tokenInfo.accRewardPerShare,
//             tokenInfo.remainingRewards,
//             tokenInfo.isActive
//         );
//     }

//     /**
//      * @dev Get current VePower for a user's positions
//      * @param user User address
//      * @return Current VePower and details of all staked positions
//      */
//     function getUserVePowerInfo(address user) external view returns (
//         uint256 currentTotalVePower,
//         uint256 lastUpdateTime,
//         uint256 positionCount
//     ) {
//         UserInfo storage userData = userInfo[user];
//         return (
//             calculateCurrentUserVePower(user),
//             userData.lastUpdateTime,
//             userData.stakedPositions.length
//         );
//     }

//     /**
//      * @dev Get global VePower model parameters
//      * @return slopeSum Total of all slopes
//      * @return offsetSum Total of all offsets
//      * @return totalVePower Current total VePower
//      */
//     function getGlobalVePowerInfo() external view returns (
//         uint256 slopeSum,
//         uint256 offsetSum,
//         uint256 totalVePower
//     ) {
//         return (
//             globalVePowerModel.slopeSum,
//             globalVePowerModel.offsetSum,
//             calculateCurrentTotalVePower()
//         );
//     }

//     /**
//      * @dev Emergency function to allow a user to force unstake their NFTs
//      * in case of a critical bug
//      * @param tokenId Token ID to force unstake
//      */
//     function emergencyUnstake(uint256 tokenId) external nonReentrant {
//         require(tokenOwners[tokenId] == msg.sender, "Not token owner");
        
//         // Find the token in user's staked positions
//         UserInfo storage userData = userInfo[msg.sender];
//         uint256 positionIndex = type(uint256).max;
        
//         for (uint256 i = 0; i < userData.stakedPositions.length; i++) {
//             if (userData.stakedPositions[i].tokenId == tokenId) {
//                 positionIndex = i;
//                 break;
//             }
//         }
        
//         require(positionIndex != type(uint256).max, "Token not found");
        
//         // Remove position from array (swap with last element and pop)
//         userData.stakedPositions[positionIndex] = userData.stakedPositions[userData.stakedPositions.length - 1];
//         userData.stakedPositions.pop();
        
//         // Remove token ownership mapping
//         delete tokenOwners[tokenId];
        
//         // Transfer veNFT back to user
//         veNFT.safeTransferFrom(address(this), msg.sender, tokenId);
        
//         // Note: Does not update rewards or vePower to save gas in emergency
//         emit Unstaked(msg.sender, tokenId);
//     }
// }