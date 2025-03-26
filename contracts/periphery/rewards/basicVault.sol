// SPDX-License-Identifier: BUSL-1.1
pragma solidity ^0.8.10;

import {Ownable} from 'contracts/dependencies/openzeppelin/contracts/Ownable.sol';
import {IERC20} from 'contracts/dependencies/openzeppelin/contracts/IERC20.sol';

contract basicVault is Ownable {

    function addReward(address transfer_strategy, address asset, uint256 amount) external onlyOwner {
        IERC20(asset).transferFrom(owner(), address(this), amount);
        IERC20(asset).approve(transfer_strategy, amount);
    }


}