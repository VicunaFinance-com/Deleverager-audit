// SPDX-License-Identifier: AGPL-3.0
pragma solidity ^0.8.0;




interface IPeggedOracle {
    function decimals() external view returns (uint8);
    function latestAnswer() external view returns (int256);
    function latestTimestamp() external view returns(uint256);
}
