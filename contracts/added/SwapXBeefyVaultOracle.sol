// SPDX-License-Identifier: BUSL-1.1
pragma solidity ^0.8.10;

import {AggregatorInterface} from "../dependencies/chainlink/AggregatorInterface.sol";
import {IERC20Metadata} from "../interfaces/IERC20Metadata.sol";
import {IPyth} from "../interfaces/IPyth.sol";
import {IBeefyVault} from "../interfaces/IBeefyVault.sol";
import {IICHIVault} from "../interfaces/IICHIVault.sol";
import {ICentralOracle} from "../interfaces/ICentralOracle.sol";

import {IVolatilityCheck} from "../interfaces/IVolatilityCheck.sol";
import {Ownable} from "../dependencies/openzeppelin/contracts/Ownable.sol";

/**
 * @title SwapXBeefyVaultOracle
 * @author Vicuna
 * @notice Oracle for Beefy vaults containing SwapX LP tokens. Gets underlying token prices from a central oracle.
 * @dev This oracle:
 *      1. Converts vault shares to LP tokens
 *      2. Gets underlying token amounts from the LP
 *      3. Gets token prices from the central oracle
 *      4. Calculates total value in USD (8 decimals)
 */
contract SwapXBeefyVaultOracle is Ownable {
    uint8 private constant _STANDARD_DECIMALS = 8;
    
    // Central oracle for getting token prices
    ICentralOracle public centralOracle;
    
    // The Beefy vault contract
    IBeefyVault public immutable vault;
    
    // The LP token that the vault holds
    IICHIVault public immutable lpToken;

    IVolatilityCheck public volatilityCheck;
    uint256 public MAX_VOLATILITY; // on 10000
    
    constructor(
        address _vault,
        address _centralOracle,
        address _volatilityCheck
    ) {
        vault = IBeefyVault(_vault);
        lpToken = IICHIVault(vault.want());
        centralOracle = ICentralOracle(_centralOracle);
        volatilityCheck = IVolatilityCheck(_volatilityCheck);
        _validateOracleHasTokens();
    }


    function setMaxVolatility(uint256 _maxVolatility) external onlyOwner {
        MAX_VOLATILITY = _maxVolatility;
    }


    /**
     * @notice Validates that the central oracle has price sources for both LP tokens
     * @dev Called in constructor to ensure oracle is properly configured
     */
    function _validateOracleHasTokens() internal view {
        require(centralOracle.getAssetSource(lpToken.token0()) != address(0), "Token0 oracle not set");
        require(centralOracle.getAssetSource(lpToken.token1()) != address(0), "Token1 oracle not set");
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
     * @notice Get the amount of underlying tokens for a given LP token amount
     * @param lpAmount Amount of LP tokens
     * @return amounts Array of token amounts [token0Amount, token1Amount]
     * @return tokens Array of token addresses [token0Address, token1Address]
     * @dev Returns arrays in the same order as the LP token's token0/token1
     */
    function getTokenAmounts(uint256 lpAmount) public view returns (uint256[] memory amounts, address[] memory tokens) {
        uint256 lpTotalSupply = lpToken.totalSupply();
        
        // Get total amounts from all positions (base, limit, and unused)
        (uint256 total0, uint256 total1) = lpToken.getTotalAmounts();
        
        // SwapX pools always have two tokens
        amounts = new uint256[](2);
        tokens = new address[](2);
        
        // Calculate proportional amounts and store with corresponding token addresses
        amounts[0] = (total0 * lpAmount) / lpTotalSupply;
        tokens[0] = lpToken.token0();

        amounts[1] = (total1 * lpAmount) / lpTotalSupply;
        tokens[1] = lpToken.token1();
        
        return (amounts, tokens);
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
     * @notice Calculate total value of tokens
     * @param amounts Array of token amounts
     * @param tokens Array of token addresses
     * @return Total value in USD (8 decimals)
     * @dev Normalizes token amounts to 18 decimals before multiplying by price
     */
    function calculateTotalValue(uint256[] memory amounts, address[] memory tokens) public view returns (uint256) {
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
     * @notice Get the latest price of a vault share
     * @return The USD value of one vault share (8 decimals)
     * @dev Calculates value by:
     *      1. Converting 1e18 shares to LP tokens
     *      2. Getting underlying token amounts
     *      3. Getting token prices from central oracle
     *      4. Calculating total value
     */
    function latestAnswer() external view returns (int256) {
        // Check volatility, to prevent exploits
        uint256 currentVolatility = volatilityCheck.currentVolatility(address(lpToken));
        require(currentVolatility <= MAX_VOLATILITY, "Volatility too high");
        // Get total supply of vault shares
        uint256 totalShares = vault.totalSupply();
        require(totalShares > 0, "No vault shares");
        
        // Convert 1 share to LP tokens
        uint256 lpAmount = sharesToLp(1e18); // Use 1e18 as base unit
        
        // Get token amounts for the LP
        (uint256[] memory amounts, address[] memory tokens) = getTokenAmounts(lpAmount);
        
        // Calculate total value
        uint256 shareValue = calculateTotalValue(amounts, tokens);
        
        return int256(shareValue);
    }

    function latestTimestamp() external view returns (uint256) {
        uint256 token0LastUpdate = centralOracle.latestTimestamp(lpToken.token0());
        uint256 token1LastUpdate = centralOracle.latestTimestamp(lpToken.token1());
        return token0LastUpdate > token1LastUpdate ? token1LastUpdate : token0LastUpdate; // return the min between both
    }

    /**
     * @notice Returns the number of decimals for price representation
     * @return Number of decimals (always 8)
     */
    function decimals() external pure returns (uint8) {
        return _STANDARD_DECIMALS;
    }
}
