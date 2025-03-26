// SPDX-License-Identifier: BUSL-1.1
pragma solidity ^0.8.10;

import {AggregatorInterface} from "../dependencies/chainlink/AggregatorInterface.sol";
import {IERC20} from "../dependencies/openzeppelin/contracts/IERC20.sol";
import {IPyth, Price} from "../interfaces/IPyth.sol";
import {Ownable} from "../dependencies/openzeppelin/contracts/Ownable.sol";
import {IPeggedOracle} from "../interfaces/IPeggedOracle.sol";

/**
 * @title CentralOracle
 * @author Vicuna
 * @notice Central price oracle that aggregates prices from multiple oracle types
 * @dev Supports:
 *      - API3 oracles
 *      - Chainlink oracles
 *      - Pyth oracles
 *      - PeggedOracle (for pegged assets)
 *      All prices are normalized to 8 decimals
 */
contract CentralOracle is Ownable {
    uint8 private constant _STANDARD_DECIMALS = 8;

    enum OracleType {
        API3,
        CHAINLINK,
        PYTH,
        PEGGEDORACLE
    }

    struct TokenConfig {
        address oracle;         // Oracle address
        bytes32 pythId;        // Pyth price feed ID (if using Pyth)
        OracleType oracleType; // Type of oracle used
    }
    
    // Mapping of token address to its oracle configuration
    mapping(address => TokenConfig) public tokens;
    
    /**
     * @notice Add or update a token's oracle configuration
     * @param token The token address
     * @param oracle The oracle address
     * @param pythId The Pyth price feed ID (if using Pyth)
     * @param oracleType The type of oracle
     * @dev Only callable by owner
     */
    function addToken(address token, address oracle, bytes32 pythId, OracleType oracleType) public onlyOwner {
        tokens[token] = TokenConfig(oracle, pythId, oracleType);
    }

    /**
     * @notice Get the oracle address for a given asset
     * @param asset The token address
     * @return The oracle address
     */
    function getAssetSource(address asset) public view returns (address) {
        return tokens[asset].oracle;
    }

    /**
     * @notice Get the normalized price (8 decimals) for a specific token
     * @param asset Token address
     * @return Token price normalized to 8 decimals
     * @dev Routes to the appropriate oracle based on the token's configuration
     */
    function getAssetPrice(address asset) public view returns (uint256) {
        TokenConfig memory config = tokens[asset];
        if (config.oracleType == OracleType.API3) {
            return getAPI3Price(config.oracle);
        } else if (config.oracleType == OracleType.CHAINLINK) {
            return getChainlinkPrice(config.oracle);
        } else if (config.oracleType == OracleType.PYTH) {
            return getPythPrice(config.oracle, config.pythId);
        } else {
            return getPeggedOraclePrice(config.oracle);
        }
    }

    function latestTimestamp(address asset) public view returns (uint256) {
        TokenConfig memory config = tokens[asset];
        if (config.oracleType == OracleType.API3) {
            return AggregatorInterface(config.oracle).latestTimestamp();
        } else if (config.oracleType == OracleType.CHAINLINK) {
            return AggregatorInterface(config.oracle).latestTimestamp();
        } else if (config.oracleType == OracleType.PYTH) {
            return IPyth(config.oracle).getPriceUnsafe(config.pythId).publishTime;
        } else {
            return IPeggedOracle(config.oracle).latestTimestamp();
        }
    }

    /**
     * @notice Get price from a PeggedOracle
     * @param oracle The PeggedOracle address
     * @return Price normalized to 8 decimals
     */
    function getPeggedOraclePrice(address oracle) public view returns(uint256) {
        int256 price = IPeggedOracle(oracle).latestAnswer();
        require(price > 0, "PeggedOracle: Invalid price");
        uint8 oracleDecimals = IPeggedOracle(oracle).decimals();
        return normalizePrice(uint256(price), oracleDecimals);
    }

    /**
     * @notice Get price from an API3 oracle
     * @param oracle The API3 oracle address
     * @return Price normalized to 8 decimals
     */
    function getAPI3Price(address oracle) public view returns (uint256) {
        AggregatorInterface source = AggregatorInterface(oracle);
        int256 price = source.latestAnswer();
        require(price > 0, "API3: Invalid price");
        
        uint8 oracleDecimals = source.decimals();
        return normalizePrice(uint256(price), oracleDecimals);
    }

    /**
     * @notice Get price from a Chainlink oracle
     * @param oracle The Chainlink oracle address
     * @return Price normalized to 8 decimals
     */
    function getChainlinkPrice(address oracle) public view returns (uint256) {
        AggregatorInterface source = AggregatorInterface(oracle);
        int256 price = source.latestAnswer();
        require(price > 0, "Chainlink: Invalid price");
        
        uint8 oracleDecimals = source.decimals();
        return normalizePrice(uint256(price), oracleDecimals);
    }

    /**
     * @notice Get price from a Pyth oracle
     * @param oracle The Pyth oracle address
     * @param priceId The Pyth price feed ID
     * @return Price normalized to 8 decimals
     */
    function getPythPrice(address oracle, bytes32 priceId) public view returns (uint256) {
        IPyth source = IPyth(oracle);
        Price memory priceData = source.getPriceUnsafe(priceId); // latestTimestamp should be checked for anyone calling this
        int64 price = priceData.price;
        require(price > 0, "Pyth: Invalid price");
        
        int32 expo = priceData.expo;
        uint8 oracleDecimals = uint8(int8(-expo));
        return normalizePrice(uint256(int256(price)), oracleDecimals);
    }

    /**
     * @notice Normalize a price to 8 decimals
     * @param price The price to normalize
     * @param oracleDecimals The number of decimals in the input price
     * @return The normalized price with 8 decimals
     */
    function normalizePrice(uint256 price, uint8 oracleDecimals) public pure returns (uint256) {
        if (oracleDecimals < _STANDARD_DECIMALS) {
            return price * (10 ** (_STANDARD_DECIMALS - oracleDecimals));
        } else if (oracleDecimals > _STANDARD_DECIMALS) {
            return price / (10 ** (oracleDecimals - _STANDARD_DECIMALS));
        }
        return price;
    }

    /**
     * @notice Returns the number of decimals used in price representation
     * @return Number of decimals (always 8)
     */
    function decimals() external pure returns (uint8) {
        return _STANDARD_DECIMALS;
    }
}