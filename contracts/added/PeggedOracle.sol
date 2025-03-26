// SPDX-License-Identifier: BUSL-1.1
pragma solidity ^0.8.10;

import {AggregatorInterface} from '../dependencies/chainlink/AggregatorInterface.sol';
import {IPyth, Price} from '../interfaces/IPyth.sol';
import {IPeggedAsset} from '../interfaces/IPeggedAsset.sol';
import {IChainlinkOracle} from '../interfaces/IChainlinkOracle.sol';

/**
 * @title PeggedOracle
 * @author Vicuna
 * @notice Contract to get asset prices of assets that does not have a feed but are pegged to another one that does
 */
contract PeggedOracle {

    enum OracleType {
        API3,
        CHAINLINK,
        PYTH
    }

    IPeggedAsset public asset;
    IPeggedAsset public peggedAsset;
    address public peggedAssetSource;
    bytes32 public pythPriceId;
    OracleType public peggedAssetOracleType;

    uint8 private constant STANDARD_DECIMALS = 8;
    int32 private constant TARGET_EXPO = -8;

  /**
   * @notice Constructor
   * @param _asset The address of the asset for which this oracle is
   * @param _peggedAsset The address of the pegged asset that has a feed
   * @param _peggedAssetSource The address of the source of pegged asset
   * @param _pythPriceId the pyth id if the pegged asset hasa pyth oracle
   * @param _peggedAssetSource the source of the pegged asset price, can be chainlink, pyth or API3
   */
  constructor(
    address _asset,
    address _peggedAsset,
    address _peggedAssetSource,
    bytes32 _pythPriceId,
    OracleType _peggedAssetOracleType
  ) {
    asset = IPeggedAsset(_asset);
    peggedAsset = IPeggedAsset(_peggedAsset);
    peggedAssetSource = _peggedAssetSource;
    pythPriceId = _pythPriceId;
    peggedAssetOracleType = _peggedAssetOracleType;
  }


  /**
   * @notice Gets the price from a Chainlink oracle
   * @return The normalized price with 8 decimals
   */
  function getChainlinkPrice() public view returns (int256) {
      IChainlinkOracle chainlinkOracle = IChainlinkOracle(peggedAssetSource);
      uint256 _decimals = chainlinkOracle.decimals();
      (, int256 price, , , ) = chainlinkOracle.latestRoundData();
      if (_decimals > STANDARD_DECIMALS) {
          price =  price / int256((10 ** (_decimals - STANDARD_DECIMALS)));
      } else if (_decimals < STANDARD_DECIMALS) {
          price = price * int256((10 ** (STANDARD_DECIMALS - _decimals)));
      }
      if (price > 0) {
          return price;
      }
      revert("Chainlink : price not found");
  }

  /**
   * @notice Gets the price from the Pyth oracle
   * @return The normalized price with 8 decimals
   */
  function getPythPrice() public view returns (int256) {
    IPyth pythOracle = IPyth(peggedAssetSource);
    Price memory priceData = pythOracle.getPriceUnsafe(pythPriceId);
    int32 expo = priceData.expo;
    int64 price = priceData.price;
    require(price > 0, "Pyth response : price is negative or null");
    // uint64 unsignedPrice = uint64(price);
    if (expo > TARGET_EXPO) {
          return price / int256((10 ** uint32(expo - TARGET_EXPO)));
      } else if (expo < TARGET_EXPO) {
          return price * int256((10 ** uint32(TARGET_EXPO - expo)));
      } else {
          return price;
      }
  }

    /**
     * @notice Gets the price from API3 Oracles
     * @return The normalized price with 8 decimals
     */
  function getAPI3Price() public view returns (int256) {
    AggregatorInterface source = AggregatorInterface(peggedAssetSource);
    int256 price = source.latestAnswer();
    uint8 _decimals = source.decimals();
    if (_decimals < STANDARD_DECIMALS) {
        price = price * int256(10**(STANDARD_DECIMALS - _decimals));
    }
    if (_decimals > STANDARD_DECIMALS) {
        price = price / int256(10**(_decimals - STANDARD_DECIMALS));
    }
    if (price > 0) {
        return price;
    }
    revert("API3 : price not found");
  }

    /**
     * @notice Gets the price of the asset
     * @return The normalized price with 8 decimals
     */
  function latestAnswer() public view returns(int256) {
    int256 peggedAssetPrice;
    if (peggedAssetOracleType == OracleType.API3) {
      peggedAssetPrice = getAPI3Price();
    } else if (peggedAssetOracleType == OracleType.CHAINLINK) {
      peggedAssetPrice =  getChainlinkPrice();
    } else if (peggedAssetOracleType == OracleType.PYTH) {
      peggedAssetPrice = getPythPrice();
    }
    // convert 1 unit of asset to pegged asset
    uint8 peggedAssetDecimals = peggedAsset.decimals();
    uint8 sourceAssetDecimals = asset.decimals();
    uint256 oneUnitWorth = asset.convertToAssets(10**peggedAssetDecimals);
    return peggedAssetPrice * int256(oneUnitWorth)/int256(10**sourceAssetDecimals);

  }

  function latestTimestamp() public view returns(uint256) {
    if (peggedAssetOracleType == OracleType.API3) {
      return IChainlinkOracle(peggedAssetSource).latestTimestamp();
    } else if (peggedAssetOracleType == OracleType.CHAINLINK) {
      return IChainlinkOracle(peggedAssetSource).latestTimestamp();
    } else if (peggedAssetOracleType == OracleType.PYTH) {
      return IPyth(peggedAssetSource).getPriceUnsafe(pythPriceId).publishTime;
    }
  }

  function decimals() public pure returns(uint8) {
    return STANDARD_DECIMALS;
  }
}
