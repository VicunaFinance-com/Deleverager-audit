// SPDX-License-Identifier: agpl-3.0
pragma solidity ^0.8.10;


interface IERC20Metadata {
  function decimals() external view returns (uint8);
  function symbol() external view returns (string memory);
}
