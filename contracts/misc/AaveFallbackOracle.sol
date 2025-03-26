// SPDX-License-Identifier: BUSL-1.1
pragma solidity ^0.8.10;

import {IChainlinkOracle} from '../interfaces/IChainlinkOracle.sol';
import {Errors} from '../protocol/libraries/helpers/Errors.sol';
import {IACLManager} from '../interfaces/IACLManager.sol';
import {IPoolAddressesProvider} from '../interfaces/IPoolAddressesProvider.sol';
import {IPriceOracleGetter} from '../interfaces/IPriceOracleGetter.sol';
import {IAaveOracle} from '../interfaces/IAaveOracle.sol';
import {IPyth, Price} from '../interfaces/IPyth.sol';

/**
 * @title AaveOracle
 * @author Aave
 * @notice Contract to get asset prices, supportts chainlink or Pyth Oracle
   will try to query chainlink first, and fallback to pyth in case chainlink is not avalaible
 */
contract AaveFallbackOracle {
  IPoolAddressesProvider public immutable ADDRESSES_PROVIDER;


  // Map of asset price sources (asset => priceSource) on chainlink
  mapping(address => address) public chainlinkAssetsSources;
  mapping(address => bytes32) public pythAssetsSources;
  address public pythOracleAddress;

  uint8 private constant STANDARD_DECIMALS = 8;
  int32 private constant TARGET_EXPO = -8;

  event AssetSourcesUpdated(address indexed asset, address chainlinkSource, bytes32 pythSource);
  event PythOracleAddressUpdated(address oldAddress, address newAddress);


  /**
   * @dev Only asset listing or pool admin can call functions marked by this modifier.
   */
  modifier onlyAssetListingOrPoolAdmins() {
    _onlyAssetListingOrPoolAdmins();
    _;
  }

  /**
   * @notice Constructor
   * @param provider The address of the new PoolAddressesProvider
   */
  constructor(
    IPoolAddressesProvider provider,
    address _pythOracleAddress
  ) {
    ADDRESSES_PROVIDER = provider;
    pythOracleAddress = _pythOracleAddress;
  }


  /**
   * @notice Sets the price feed sources for a list of assets
   * @param assets The addresses of the assets
   * @param chainlinkSources The addresses of the Chainlink price feeds
   * @param pythFeedId The Pyth price feed IDs
   */
  function setAssetSources(
    address[] calldata assets,
    address[] calldata chainlinkSources,
    bytes32[] calldata pythFeedId
  ) external onlyAssetListingOrPoolAdmins {
    _setAssetsSources(assets, chainlinkSources, pythFeedId);
  }

  /**
   * @notice Internal function to set the sources for each asset
   * @param assets The addresses of the assets
   * @param chainlinkSources The address of the chainlink source of each asset
   * @param pythFeedId the feed id of pyth for each asset
   */
  function _setAssetsSources(address[] memory assets, address[] memory chainlinkSources, bytes32[] memory pythFeedId) internal {
    require(assets.length == chainlinkSources.length, Errors.INCONSISTENT_PARAMS_LENGTH);
    require(assets.length == pythFeedId.length, Errors.INCONSISTENT_PARAMS_LENGTH);
    for (uint256 i = 0; i < assets.length; i++) {
      chainlinkAssetsSources[assets[i]] = chainlinkSources[i];
      pythAssetsSources[assets[i]] = pythFeedId[i];
      emit AssetSourcesUpdated(assets[i], chainlinkSources[i], pythFeedId[i]);
    }

  }

  /**
   * @notice Updates the Pyth oracle address
   * @param newAddress The new Pyth oracle address
   */
  function setPythOracleAddress(address newAddress) external onlyAssetListingOrPoolAdmins {
    require(newAddress != address(0), "Invalid address");
    address oldAddress = pythOracleAddress;
    pythOracleAddress = newAddress;
    emit PythOracleAddressUpdated(oldAddress, newAddress);
}


  /**
   * @notice Gets the price from a Chainlink oracle
   * @param sourceAddress The address of the Chainlink price feed
   * @return The normalized price with 8 decimals
   */
  function getChainlinkPrice(address sourceAddress) public view returns (uint256) {
    IChainlinkOracle chainlinkOracle = IChainlinkOracle(sourceAddress);
      uint256 decimals = chainlinkOracle.decimals();
      (, int256 price, , , ) = chainlinkOracle.latestRoundData();
      if (decimals > STANDARD_DECIMALS) {
          return uint256(price) / (10 ** (decimals - STANDARD_DECIMALS));
      } else if (decimals < STANDARD_DECIMALS) {
          return uint256(price) * (10 ** (STANDARD_DECIMALS - decimals));
      }
      return uint256(price);
  }

  /**
   * @notice Gets the price from the Pyth oracle
   * @param pythPriceId The Pyth price feed ID
   * @return The normalized price with 8 decimals
   */
  function getPythPrice(bytes32 pythPriceId) public view returns (uint256) {
    IPyth pythOracle = IPyth(pythOracleAddress);
    Price memory priceData = pythOracle.getPriceNoOlderThan(pythPriceId, 3600);
    int32 expo = priceData.expo;
    int64 price = priceData.price;
    require(price > 0, "Pyth response : price is negative or null");
    uint64 unsignedPrice = uint64(price);
    if (expo > TARGET_EXPO) {
          return unsignedPrice / (10 ** uint32(expo - TARGET_EXPO));
      } else if (expo < TARGET_EXPO) {
          return unsignedPrice * (10 ** uint32(TARGET_EXPO - expo));
      } else {
          return unsignedPrice;
      }
  }

  /**
   * @notice Gets the price of an asset, trying Chainlink first then Pyth as fallback
   * @param asset The address of the asset
   * @return The normalized price with 8 decimals
   */
  function getAssetPrice(address asset) public view returns (uint256) {
    address chainLinkSourceAddress = chainlinkAssetsSources[asset];
    bytes32 pythPriceId = pythAssetsSources[asset];
    uint256 price;
    if (chainLinkSourceAddress != address(0)) {
      price = getChainlinkPrice(chainLinkSourceAddress);
      if (price  == 0 && pythPriceId != bytes32(0)) {
        price = getPythPrice(pythPriceId);
      }
    } else if (pythPriceId != bytes32(0)) {
      price = getPythPrice(pythPriceId);
    }
    if (price > 0) {
      return price;
    }
    revert("No reliable price source found");
  }

  /**
   * @notice Gets the prices for a list of assets
   * @param assets The addresses of the assets
   * @return An array of normalized prices with 8 decimals
   */
  function getAssetsPrices(
    address[] calldata assets
  ) external view returns (uint256[] memory) {
    uint256[] memory prices = new uint256[](assets.length);
    for (uint256 i = 0; i < assets.length; i++) {
      prices[i] = getAssetPrice(assets[i]);
    }
    return prices;
  }

  /**
   * @notice Gets both Chainlink and Pyth sources for an asset
   * @param asset The address of the asset
   * @return The Chainlink source address and Pyth price feed ID
   */
  function getSourceOfAsset(address asset) external view returns (address, bytes32) {
    return (chainlinkAssetsSources[asset], pythAssetsSources[asset]);
  }

  /**
   * @dev Checks if the caller has asset listing or pool admin rights
   */
  function _onlyAssetListingOrPoolAdmins() internal view {
    IACLManager aclManager = IACLManager(ADDRESSES_PROVIDER.getACLManager());
    require(
      aclManager.isAssetListingAdmin(msg.sender) || aclManager.isPoolAdmin(msg.sender),
      Errors.CALLER_NOT_ASSET_LISTING_OR_POOL_ADMIN
    );
  }
}
