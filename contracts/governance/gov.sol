// SPDX-License-Identifier: MIT
pragma solidity ^0.8.10;

import "@openzeppelin/contracts/token/ERC721/ERC721.sol";
import "@openzeppelin/contracts/token/ERC721/extensions/ERC721Enumerable.sol";
import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/utils/math/Math.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import "@openzeppelin/contracts/utils/Counters.sol";

/**
 * @title VeNFT
 * @dev Contract for creating vote-escrowed NFTs by locking LP tokens
 * Implements linear decay of voting power over time (veCRV model)
 */
contract VeNFT is ERC721Enumerable, Ownable {
    using SafeERC20 for IERC20;
    using Counters for Counters.Counter;

    Counters.Counter private _tokenIdCounter;

    // LP token to lock
    IERC20 public lpToken;

    // Maximum lock time in seconds (24 months = 2 years)
    uint256 public constant MAX_LOCK_DURATION = 730 days; // ~24 months
    
    // Reference value for UI display only (30 days)
    uint256 public constant MONTH = 30 days;

    struct LockInfo {
        uint256 amount;       // Amount of LP tokens locked
        uint256 startTime;    // When the lock started
        uint256 endTime;      // When the lock will end
        uint256 lockDuration; // Duration in seconds
    }

    // TokenId => LockInfo
    mapping(uint256 => LockInfo) public locks;

    // Events
    event LPLocked(address indexed user, uint256 tokenId, uint256 amount, uint256 duration);
    event LockExtended(uint256 oldTokenId, uint256 newTokenId, uint256 newDuration);
    event LocksMerged(uint256 tokenId1, uint256 tokenId2, uint256 newTokenId);

    /**
     * @dev Constructor
     * @param _lpToken Address of the LP token to lock
     */
    constructor(address _lpToken) ERC721("Vote Escrowed NFT", "veNFT") Ownable() {
        require(_lpToken != address(0), "Invalid LP token address");
        lpToken = IERC20(_lpToken);
    }

    /**
     * @dev Creates a veNFT by locking LP tokens
     * @param amount Amount of LP tokens to lock
     * @param durationInSeconds Lock duration in seconds (max is MAX_LOCK_DURATION)
     * @return tokenId The ID of the minted NFT
     */
    function createLock(uint256 amount, uint256 durationInSeconds) external returns (uint256) {
        require(amount > 0, "Amount must be greater than 0");
        require(durationInSeconds > 0 && durationInSeconds <= MAX_LOCK_DURATION, "Invalid lock duration");

        // Transfer LP tokens from user to contract
        lpToken.safeTransferFrom(msg.sender, address(this), amount);

        // Calculate lock end time
        uint256 startTime = block.timestamp;
        uint256 endTime = startTime + durationInSeconds;

        // Mint NFT
        uint256 tokenId = _tokenIdCounter.current();
        _tokenIdCounter.increment();
        _mint(msg.sender, tokenId);

        // Store lock information
        locks[tokenId] = LockInfo({
            amount: amount,
            startTime: startTime,
            endTime: endTime,
            lockDuration: durationInSeconds
        });
        
        emit LPLocked(msg.sender, tokenId, amount, durationInSeconds);

        return tokenId;
    }

    /**
     * @dev Extends the lock duration for an existing veNFT
     * @param tokenId The ID of the NFT to extend
     * @param additionalSeconds Additional seconds to extend the lock by
     * @return newTokenId The ID of the new NFT
     */
    function extendLock(uint256 tokenId, uint256 additionalSeconds) external returns (uint256) {
        require(_isApprovedOrOwner(msg.sender, tokenId), "Not owner nor approved");
        require(additionalSeconds > 0, "Must extend by some time");

        LockInfo memory lock = locks[tokenId];
        
        // Calculate remaining time in seconds
        uint256 remainingSeconds = 0;
        if (lock.endTime > block.timestamp) {
            remainingSeconds = lock.endTime - block.timestamp;
        }
        
        // Calculate new total duration (remaining + additional)
        uint256 newTotalDuration = remainingSeconds + additionalSeconds;
        
        // Cap at maximum lock duration
        if (newTotalDuration > MAX_LOCK_DURATION) {
            newTotalDuration = MAX_LOCK_DURATION;
        }

        // Burn the old NFT
        _burn(tokenId);

        // Mint a new NFT
        uint256 newTokenId = _tokenIdCounter.current();
        _tokenIdCounter.increment();
        _mint(msg.sender, newTokenId);

        // Calculate new end time
        uint256 startTime = block.timestamp;
        uint256 endTime = startTime + newTotalDuration;

        // Create new lock with same amount but updated duration
        locks[newTokenId] = LockInfo({
            amount: lock.amount,
            startTime: startTime,
            endTime: endTime,
            lockDuration: newTotalDuration
        });

        // Remove old lock info
        delete locks[tokenId];
        
        emit LockExtended(tokenId, newTokenId, newTotalDuration);

        return newTokenId;
    }

    /**
     * @dev Merges two veNFTs into a new one
     * @param tokenId1 First NFT to merge
     * @param tokenId2 Second NFT to merge
     * @return newTokenId The ID of the merged NFT
     */
    function mergeLocks(uint256 tokenId1, uint256 tokenId2) external returns (uint256) {
        require(_isApprovedOrOwner(msg.sender, tokenId1), "Not owner of first token");
        require(_isApprovedOrOwner(msg.sender, tokenId2), "Not owner of second token");
        require(tokenId1 != tokenId2, "Cannot merge same token");

        LockInfo memory lock1 = locks[tokenId1];
        LockInfo memory lock2 = locks[tokenId2];

        // Calculate total LP amount
        uint256 totalAmount = lock1.amount + lock2.amount;
        require(totalAmount > 0, "Total amount must be greater than 0");

        // Step 1: Calculate VePower coefficient (0-1) for each position
        // VePower = remainingTime / MAX_LOCK_DURATION
        uint256 vePower1 = 0;
        if (lock1.endTime > block.timestamp) {
            vePower1 = (lock1.endTime - block.timestamp) * 1e18 / MAX_LOCK_DURATION;
        }
        
        uint256 vePower2 = 0;
        if (lock2.endTime > block.timestamp) {
            vePower2 = (lock2.endTime - block.timestamp) * 1e18 / MAX_LOCK_DURATION;
        }
        
        // Step 2: Calculate total VePower (weighted average)
        // Total VePower = ((VePower1 × LP1) + (VePower2 × LP2)) / (LP1 + LP2)
        uint256 totalVePower = ((vePower1 * lock1.amount) + (vePower2 * lock2.amount)) / totalAmount;
        
        // Step 3: Calculate new lockup duration
        // New Lockup Duration = Total VePower × MAX_LOCK_DURATION
        uint256 newDuration = (totalVePower * MAX_LOCK_DURATION) / 1e18;
        
        // Ensure minimum and maximum duration
        if (newDuration > MAX_LOCK_DURATION) {
            newDuration = MAX_LOCK_DURATION;
        }
        
        if (newDuration < 1 days) {
            newDuration = 1 days;
        }

        // Burn old NFTs
        _burn(tokenId1);
        _burn(tokenId2);

        // Mint new NFT
        uint256 newTokenId = _tokenIdCounter.current();
        _tokenIdCounter.increment();
        _mint(msg.sender, newTokenId);

        // Calculate end time for new NFT
        uint256 startTime = block.timestamp;
        uint256 endTime = startTime + newDuration;

        // Create new lock
        locks[newTokenId] = LockInfo({
            amount: totalAmount,
            startTime: startTime,
            endTime: endTime,
            lockDuration: newDuration
        });

        // Remove old lock info
        delete locks[tokenId1];
        delete locks[tokenId2];

        emit LocksMerged(tokenId1, tokenId2, newTokenId);

        return newTokenId;
    }

    /**
     * @dev Gets all tokens owned by an address
     * @param owner Address to query
     * @return tokenIds Array of token IDs owned by the address
     */
    function getTokensOfOwner(address owner) public view returns (uint256[] memory) {
        uint256 tokenCount = balanceOf(owner);
        
        if (tokenCount == 0) {
            return new uint256[](0);
        }
        
        uint256[] memory tokenIds = new uint256[](tokenCount);
        for (uint256 i = 0; i < tokenCount; i++) {
            tokenIds[i] = tokenOfOwnerByIndex(owner, i);
        }
        
        return tokenIds;
    }

    /**
     * @dev Withdraws LP tokens after lock period ends
     * @param tokenId The ID of the NFT to withdraw
     */
    function withdraw(uint256 tokenId) external {
        require(_isApprovedOrOwner(msg.sender, tokenId), "Not owner nor approved");
        
        LockInfo memory lock = locks[tokenId];
        require(block.timestamp >= lock.endTime, "Lock period not ended");

        // Burn the NFT
        _burn(tokenId);

        // Transfer LP tokens back to user
        lpToken.safeTransfer(msg.sender, lock.amount);

        // Remove lock info
        delete locks[tokenId];
    }

    /**
     * @dev Calculates the current vePower for a token based on remaining time
     * vePower decays linearly over time (veCRV model)
     * @param tokenId The ID of the NFT
     * @return Current vePower (same decimals as LP token)
     */
    function getCurrentVePower(uint256 tokenId) public view returns (uint256) {
        require(_exists(tokenId), "Token does not exist");
        
        LockInfo memory lock = locks[tokenId];
        
        // If lock has expired, vePower is 0
        if (block.timestamp >= lock.endTime) {
            return 0;
        }
        
        // Calculate remaining time
        uint256 remainingTime = lock.endTime - block.timestamp;
        
        // Calculate vePower based on remaining time
        // vePower = amount * (remainingTime / MAX_TIME)
        uint256 vePower = (lock.amount * remainingTime) / MAX_LOCK_DURATION;
        
        return vePower;
    }
    
    /**
     * @dev Gets all tokens owned by an address with their full metadata
     * @param owner Address to query
     * @return tokenIds Array of token IDs owned by the address
     * @return lockInfos Array of LockInfo structs for each token
     * @return vePowers Array of current vePowers for each token
     */
    function getAllUserNFTs(address owner) external view returns (
        uint256[] memory tokenIds,
        LockInfo[] memory lockInfos,
        uint256[] memory vePowers
    ) {
        tokenIds = getTokensOfOwner(owner);
        uint256 tokenCount = tokenIds.length;
        
        lockInfos = new LockInfo[](tokenCount);
        vePowers = new uint256[](tokenCount);
        
        for (uint256 i = 0; i < tokenCount; i++) {
            uint256 tokenId = tokenIds[i];
            lockInfos[i] = locks[tokenId];
            vePowers[i] = getCurrentVePower(tokenId);
        }
        
        return (tokenIds, lockInfos, vePowers);
    }
    
    /**
     * @dev Gets the total vePower of all tokens owned by an address
     * @param owner Address to query
     * @return totalVePower Sum of vePower across all owned tokens
     */
    function getTotalVePowerForOwner(address owner) external view returns (uint256) {
        uint256[] memory tokenIds = getTokensOfOwner(owner);
        uint256 totalVePower = 0;
        
        for (uint256 i = 0; i < tokenIds.length; i++) {
            totalVePower += getCurrentVePower(tokenIds[i]);
        }
        
        return totalVePower;
    }

    /**
     * @dev Returns information about a specific veNFT including current vePower
     * @param tokenId The ID of the NFT
     * @return lockInfo The lock information
     * @return currentVePower The current vePower
     */
    function getLockInfo(uint256 tokenId) external view returns (LockInfo memory lockInfo, uint256 currentVePower) {
        require(_exists(tokenId), "Token does not exist");
        lockInfo = locks[tokenId];
        currentVePower = getCurrentVePower(tokenId);
        return (lockInfo, currentVePower);
    }
    
    /**
     * @dev Previews the vePower that would result from creating a new lock
     * @param amount Amount of LP tokens to lock
     * @param durationInSeconds Lock duration in seconds
     * @return predictedVePower The vePower the new lock would have
     */
    function previewCreateLock(uint256 amount, uint256 durationInSeconds) external pure returns (uint256 predictedVePower) {
        // Cap duration to maximum
        if (durationInSeconds > MAX_LOCK_DURATION) {
            durationInSeconds = MAX_LOCK_DURATION;
        }
        
        // vePower = amount * (duration / MAX_DURATION)
        predictedVePower = (amount * durationInSeconds) / MAX_LOCK_DURATION;
        
        return predictedVePower;
    }
    
    /**
     * @dev Previews the vePower that would result from extending a lock
     * @param tokenId The ID of the NFT to be extended
     * @param additionalSeconds Additional seconds to extend the lock by
     * @return predictedVePower The vePower the extended lock would have
     */
    function previewExtendLock(uint256 tokenId, uint256 additionalSeconds) external view returns (uint256 predictedVePower) {
        require(_exists(tokenId), "Token does not exist");
        
        LockInfo memory lock = locks[tokenId];
        
        // Calculate remaining time in seconds
        uint256 remainingSeconds = 0;
        if (lock.endTime > block.timestamp) {
            remainingSeconds = lock.endTime - block.timestamp;
        }
        
        // Calculate new total duration (remaining + additional)
        uint256 newTotalDuration = remainingSeconds + additionalSeconds;
        
        // Cap at maximum lock duration
        if (newTotalDuration > MAX_LOCK_DURATION) {
            newTotalDuration = MAX_LOCK_DURATION;
        }
        
        // Calculate predicted vePower
        predictedVePower = (lock.amount * newTotalDuration) / MAX_LOCK_DURATION;
        
        return predictedVePower;
    }
    
    /**
     * @dev Previews the vePower that would result from merging two locks
     * @param tokenId1 First NFT to merge
     * @param tokenId2 Second NFT to merge
     * @return predictedVePower The vePower the merged lock would have
     * @return newDuration The duration of the merged lock in seconds
     * @return totalAmount The total LP amount of the merged lock
     */
    function previewMergeLocks(uint256 tokenId1, uint256 tokenId2) external view returns (
        uint256 predictedVePower, 
        uint256 newDuration,
        uint256 totalAmount
    ) {
        require(_exists(tokenId1) && _exists(tokenId2), "Tokens do not exist");
        require(tokenId1 != tokenId2, "Cannot merge same token");
        
        LockInfo memory lock1 = locks[tokenId1];
        LockInfo memory lock2 = locks[tokenId2];
        
        // Calculate total LP amount
        totalAmount = lock1.amount + lock2.amount;
        if (totalAmount == 0) return (0, 0, 0);
        
        // Step 1: Calculate VePower coefficient (0-1) for each position
        uint256 vePower1 = 0;
        if (lock1.endTime > block.timestamp) {
            vePower1 = (lock1.endTime - block.timestamp) * 1e18 / MAX_LOCK_DURATION;
        }
        
        uint256 vePower2 = 0;
        if (lock2.endTime > block.timestamp) {
            vePower2 = (lock2.endTime - block.timestamp) * 1e18 / MAX_LOCK_DURATION;
        }
        
        // Step 2: Calculate total VePower (weighted average)
        uint256 totalVePower = ((vePower1 * lock1.amount) + (vePower2 * lock2.amount)) / totalAmount;
        
        // Step 3: Calculate new lockup duration
        newDuration = (totalVePower * MAX_LOCK_DURATION) / 1e18;
        
        // Ensure minimum and maximum duration
        if (newDuration > MAX_LOCK_DURATION) {
            newDuration = MAX_LOCK_DURATION;
        }
        
        if (newDuration < 1 days) {
            newDuration = 1 days;
        }
        
        // Calculate predicted vePower with the new duration
        predictedVePower = (totalAmount * newDuration) / MAX_LOCK_DURATION;
        
        return (predictedVePower, newDuration, totalAmount);
    }

    /**
     * @dev Checks if a token exists - uses OpenZeppelin's internal implementation
     * @param tokenId The ID of the NFT
     * @return bool Whether the token exists
     */
    function exists(uint256 tokenId) internal view returns (bool) {
        return _exists(tokenId);
    }

    /**
     * @dev Returns URI for token metadata
     * @param tokenId The ID of the NFT
     * @return string The token URI
     */
    function tokenURI(uint256 tokenId) public view override returns (string memory) {
        require(_exists(tokenId), "Token does not exist");
        
        LockInfo memory lock = locks[tokenId];
        uint256 currentVePower = getCurrentVePower(tokenId);
        
        // Convert lockDuration from seconds to days for more human-readable display
        uint256 durationDays = lock.lockDuration / 1 days;
        
        // Calculate remaining time in days
        uint256 remainingDays = 0;
        if (lock.endTime > block.timestamp) {
            remainingDays = (lock.endTime - block.timestamp) / 1 days;
        }
        
        
        // Base JSON structure for the NFT metadata
        return string(
            abi.encodePacked(
                'data:application/json;base64,',
                Base64.encode(
                    bytes(
                        string(
                            abi.encodePacked(
                                '{"name":"veNFT #',
                                toString(tokenId),
                                '","description":"Vote Escrowed NFT for locked LP tokens","attributes":[',
                                '{"trait_type":"LP Amount","value":"',
                                toString(lock.amount),
                                '"},{"trait_type":"Lock Duration","value":"',
                                toString(durationDays),
                                ' days"},{"trait_type":"Current VePower","value":"',
                                toString(currentVePower),
                                '%"},{"trait_type":"Remaining Time","value":"',
                                toString(remainingDays),
                                ' days"},{"trait_type":"End Date (Timestamp)","value":"',
                                toString(lock.endTime),
                                '"}]}'
                            )
                        )
                    )
                )
            )
        );
    }

    /**
     * @dev Converts a uint to a string
     * @param value The uint to convert
     * @return string The resulting string
     */
    function toString(uint256 value) internal pure returns (string memory) {
        if (value == 0) {
            return "0";
        }
        uint256 temp = value;
        uint256 digits;
        while (temp != 0) {
            digits++;
            temp /= 10;
        }
        bytes memory buffer = new bytes(digits);
        while (value != 0) {
            digits -= 1;
            buffer[digits] = bytes1(uint8(48 + uint256(value % 10)));
            value /= 10;
        }
        return string(buffer);
    }
}


/**
 * @title Base64
 * @dev Base64 encoding library for generating token URIs
 */
library Base64 {
    string internal constant TABLE = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";

    function encode(bytes memory data) internal pure returns (string memory) {
        if (data.length == 0) return "";
        
        // Output length: 4 * ceil(input_length / 3)
        uint256 encodedLen = 4 * ((data.length + 2) / 3);
        
        // Create the return variable of proper size
        string memory result = new string(encodedLen);
        bytes memory resultBytes = bytes(result);
        
        uint256 i = 0;
        uint256 j = 0;
        
        for (; i < data.length; i += 3) {
            // Get next 3 bytes (if available)
            uint256 a = i < data.length ? uint8(data[i]) : 0;
            uint256 b = i + 1 < data.length ? uint8(data[i + 1]) : 0;
            uint256 c = i + 2 < data.length ? uint8(data[i + 2]) : 0;
            
            uint256 triple = (a << 16) | (b << 8) | c;
            
            // Process 4 characters
            resultBytes[j++] = bytes(TABLE)[uint8((triple >> 18) & 0x3F)];
            resultBytes[j++] = bytes(TABLE)[uint8((triple >> 12) & 0x3F)];
            resultBytes[j++] = i + 1 < data.length ? bytes(TABLE)[uint8((triple >> 6) & 0x3F)] : bytes1('=');
            resultBytes[j++] = i + 2 < data.length ? bytes(TABLE)[uint8(triple & 0x3F)] : bytes1('=');
        }
        
        return result;
    }
}