// SPDX-License-Identifier: AGPL-3.0
pragma solidity ^0.8.0;




interface ICentralOracle {
    function decimals() external view returns (uint8);
    function getAssetPrice(address asset) external view returns (uint256);
    function getAssetSource(address asset) external view returns (address);
    function latestTimestamp(address asset) external view returns(uint256);
}
