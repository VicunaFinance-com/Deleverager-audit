// SPDX-License-Identifier: AGPL-3.0
pragma solidity ^0.8.0;




interface IPeggedAsset {
    function decimals() external view returns (uint8);
    function convertToAssets(uint256 amount) external view returns (uint256);
}
