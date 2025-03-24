// SPDX-License-Identifier: BUSL-1.1
pragma solidity ^0.8.10;

interface ILeveragerRights {
    function setBorrowPool(address _borrowPool) external;
    function setPool(address _borrowPool) external;
    function pool() external view returns (address);
    function borrowPool() external view returns (address);
}
