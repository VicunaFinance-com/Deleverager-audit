// SPDX-License-Identifier: AGPL-3.0
pragma solidity ^0.8.0;

import {IFlashLoanSimpleReceiver} from '../interfaces/IFlashLoanSimpleReceiver.sol';
import {IPoolAddressesProvider} from '../../interfaces/IPoolAddressesProvider.sol';
import {IPool} from '../../interfaces/IPool.sol';
import {IERC20} from '../../dependencies/openzeppelin/contracts/IERC20.sol';

/**
 * @title FlashLoanSimpleReceiverBase
 * @author Aave
 * @notice Base contract to develop a flashloan-receiver contract.
 */
contract FlashLoanSimpleReceiverBase{
  IPoolAddressesProvider public immutable ADDRESSES_PROVIDER;
  IPool public immutable POOL;

  constructor(IPoolAddressesProvider provider) {
    ADDRESSES_PROVIDER = provider;
    POOL = IPool(provider.getPool());
  }

  function call(address[] calldata assets,
    uint256[] calldata amounts,
    uint256[] calldata interestRateModes) external {

    POOL.flashLoan(address(this), assets, amounts, interestRateModes, address(this), bytes(""), 0);
  }


  function executeOperation(
    address[] calldata assets,
    uint256[] calldata amounts,
    uint256[] calldata premiums,
    address initiator,
    bytes calldata params
  ) external returns (bool) {
    address asset = assets[0];
    uint256 amount = amounts[0];
    uint256 premium = premiums[0];
    uint256 totalToSend = amount + premium;
    IERC20(asset).approve(address(POOL), totalToSend);
    return true;
  }
}
