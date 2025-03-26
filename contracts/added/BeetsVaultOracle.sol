// SPDX-License-Identifier: BUSL-1.1
pragma solidity ^0.8.10;

import {AggregatorInterface} from "../dependencies/chainlink/AggregatorInterface.sol";
import {IERC20Metadata} from "../interfaces/IERC20Metadata.sol";
import {IPyth} from "../interfaces/IPyth.sol";
import {IBeefyVault} from "../interfaces/IBeefyVault.sol";
import {IICHIVault} from "../interfaces/IICHIVault.sol";
import {ICentralOracle} from "../interfaces/ICentralOracle.sol";
import {IERC20} from "../dependencies/openzeppelin/contracts/IERC20.sol";
import {VaultReentrancyLib, IVault} from "./VaultReentrancyLib.sol";

// Empty struct for the manageUserBalance call

// Empty struct for the manageUserBalance call
interface IBeetsPool {
    function getPoolId() external view returns (bytes32);

    function getRate() external view returns (uint256);

    function getVault() external view returns (address);

    function getActualSupply() external view returns (uint256);

    function totalSupply() external view returns (uint256);

    function balanceOf(address account) external view returns (uint256);

    function transfer(address recipient, uint256 amount) external returns (bool);
}

interface IBeetsVaultV2 {
    function getPoolTokens(
        bytes32
    ) external view returns (address[] memory, uint256[] memory, uint256);
}

/**
 * @title BeefyVaultOracle
 * @author Vicuna
 * @notice Contract to get the price of a Beefy vault share by calculating the value of underlying LP tokens
 */
contract BeetsVaultOracle {
    uint8 private constant _STANDARD_DECIMALS = 8;

    // Central oracle for getting token prices
    ICentralOracle public centralOracle;

    // The Beefy vault contract
    IBeefyVault public immutable vault;

    // The LP token that the vault holds
    IICHIVault public immutable lpToken;

    /**
     * @notice Constructor
     * @param _vault The Beefy vault address
     * @param _centralOracle The central oracle address that provides token prices
     * @dev Validates that the central oracle has price sources for both LP tokens
     */
    constructor(address _vault, address _centralOracle) {
        vault = IBeefyVault(_vault);
        lpToken = IICHIVault(vault.want());
        centralOracle = ICentralOracle(_centralOracle);
        _validateOracleHasTokens();
    }

    function _checkForBalReentrancy() internal view {
        IBeetsPool pool = IBeetsPool(vault.want());
        IVault poolVault = IVault(pool.getVault());
        VaultReentrancyLib.ensureNotInVaultContext(poolVault);
    }

    /**
     * @notice Validates that the central oracle has price sources for both LP tokens
     * @dev Called in constructor to ensure oracle is properly configured
     */
    function _validateOracleHasTokens() internal view {
        IBeetsPool pool = IBeetsPool(vault.want());
        bytes32 poolId = pool.getPoolId();
        IBeetsVaultV2 poolVault = IBeetsVaultV2(pool.getVault());
        (address[] memory _tokens, , ) = poolVault.getPoolTokens(poolId);
        // Get total amounts from all positions (base, limit, and unused)

        // Create amounts array matching tokens array order
        uint256 outputLength = _tokens.length;

        for (uint256 outputIdx = 0; outputIdx < outputLength; outputIdx++) {
            if (_tokens[outputIdx] == address(pool)) {
                continue;
            }
            require(
                centralOracle.getAssetSource(_tokens[outputIdx]) != address(0),
                "One of the token oracle not set"
            );
        }
    }

    /**
     * @notice Convert vault shares to LP tokens
     * @param shareAmount Amount of vault shares
     * @return LP token amount (in LP token decimals)
     */
    function sharesToLp(uint256 shareAmount) public view returns (uint256) {
        uint256 pricePerFullShare = vault.getPricePerFullShare();
        return (shareAmount * pricePerFullShare) / 1e18;
    }

    /**
     * @notice Get the total amount of tokens in the pool
     * @return values Array of token amounts
     * @return tokens Array of token addresses
     */
    function getTotalTokensInPool()
        public
        view
        returns (uint256[] memory values, address[] memory tokens)
    {
        IBeetsPool pool = IBeetsPool(vault.want());
        bytes32 poolId = pool.getPoolId();
        IBeetsVaultV2 poolVault = IBeetsVaultV2(pool.getVault());
        (address[] memory _tokens, uint256[] memory _balances, ) = poolVault.getPoolTokens(poolId);

        uint256 outputLength = _tokens.length;
        values = new uint256[](outputLength - 1);
        tokens = new address[](outputLength - 1);

        uint256 skippingIndex = 0;
        for (uint256 outputIdx = 0; outputIdx < outputLength; outputIdx++) {
            if (_tokens[outputIdx] == address(pool)) {
                skippingIndex++;
                continue;
            }
            values[outputIdx - skippingIndex] = _balances[outputIdx];
            tokens[outputIdx - skippingIndex] = _tokens[outputIdx];
        }
    }

    /**
     * @notice Get the amount of underlying tokens for a given share amount. mainly used for liquidation bot
     * @param shareAmount Amount of vault LP token
     * @return amounts Array of token amounts [token0Amount, token1Amount]
     * @return tokens Array of token addresses [token0Address, token1Address]
     * @dev Returns arrays in the same order as the LP token's token0/token1
     */
    function getTokenAmountsForShare(
        uint256 shareAmount
    ) public view returns (uint256[] memory amounts, address[] memory tokens) {
        uint256 lpAmount = sharesToLp(shareAmount);
        (amounts, tokens) = getTotalTokensInPool();
        uint256 actualSupply = IBeetsPool(vault.want()).getActualSupply();
        for (uint256 i = 0; i < amounts.length; i++) {
            amounts[i] = (amounts[i] * lpAmount) / actualSupply;
        }
    }

    /**
     * @notice Get the normalized price (8 decimals) for a specific token
     * @param token Token address
     * @return Token price in USD with 8 decimals
     * @dev Queries the central oracle which handles price normalization
     */
    function getTokenPrice(address token) public view returns (uint256) {
        return centralOracle.getAssetPrice(token);
    }

    /**
     * @notice Calculate total value of tokens in input
     * @param amounts Array of token amounts
     * @param tokens Array of token addresses
     * @return Total value in USD (8 decimals)
     * @dev Normalizes token amounts to 18 decimals before multiplying by price
     */
    function calculateTotalValue(
        uint256[] memory amounts,
        address[] memory tokens
    ) public view returns (uint256) {
        require(amounts.length == tokens.length, "Length mismatch");

        uint256 totalValue = 0;
        for (uint256 i = 0; i < amounts.length; i++) {
            address token = tokens[i];
            uint8 tokenDecimals = IERC20Metadata(token).decimals();
            uint256 tokenPrice = getTokenPrice(token);

            // Convert token amount to 18 decimals (multiply by missing decimals)
            uint256 normalizedAmount = amounts[i] * (10 ** (18 - tokenDecimals));

            // Multiply by price (8 decimals) and divide by 18 decimals to get value in 8 decimals
            totalValue += (normalizedAmount * tokenPrice) / 1e18;
        }

        return totalValue;
    }

    /**
     * @notice Get the price of a BPT token
     * @return The USD value of one BPT token (8 decimals)
     * @dev Calculates value by:
     *      1. Getting total token amounts in pool
     *      2. Getting token prices from central oracle
     *      3. Calculating total value of pool
     *      4. Dividing by total supply of BPT tokens
     */
    function getBPTPrice() public view returns (int256) {
        _checkForBalReentrancy();
        (uint256[] memory amounts, address[] memory tokens) = getTotalTokensInPool();
        // Calculate total value
        uint256 totalValue = calculateTotalValue(amounts, tokens);
        IBeetsPool pool = IBeetsPool(vault.want());
        return int256(((totalValue * 1e18) / pool.getActualSupply()));
    }

    /**
     * @notice Get the  price of a vault share
     * @return The USD value of one vault share (8 decimals)
     * @dev Calculates value by:
     *      1. Getting price of one BPT token
     *      2. Multiplying by BPT token amount for one vault share
     */
    function latestAnswer() external view returns (int256) {
        _checkForBalReentrancy();
        // Get total supply of vault shares
        uint256 totalShares = vault.totalSupply();
        require(totalShares > 0, "No vault shares");

        return int256((uint256(getBPTPrice()) * sharesToLp(1e18)) / 1e18);
    }

    /**
     * @notice Returns the latest timestamp of update of the price of the vault share
     * @dev as multiple tokens are involved, return the earliest timestamp of all tokens
     * @return Latest timestamp
     */
    function latestTimestamp() external view returns (uint256) {
        (, address[] memory tokens) = getTotalTokensInPool();
        uint256 earlierTimestamp = block.timestamp;
        for (uint256 i = 0; i < tokens.length; i++) {
            uint256 tokenTimestamp = centralOracle.latestTimestamp(tokens[i]);
            if (tokenTimestamp < earlierTimestamp) {
                earlierTimestamp = tokenTimestamp;
            }
        }
        return earlierTimestamp;
    }

    /**
     * @notice Returns the number of decimals for price representation
     * @return Number of decimals (always 8)
     */
    function decimals() external pure returns (uint8) {
        return _STANDARD_DECIMALS;
    }
}
