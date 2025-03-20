// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

interface IBeefyVault {
    /**
     * @notice Gets the total supply of vault shares
     * @return Total supply of shares
     */
    function totalSupply() external view returns (uint256);

    /**
     * @notice Function for various UIs to display the current value of one of our yield tokens.
     * @return An uint256 with 18 decimals of how much underlying asset one vault share represents.
     */
    function getPricePerFullShare() external view returns (uint256);

    function want() external view returns (address);

    function deposit(uint256 amount) external;
    function transfer(address recipient, uint256 amount) external returns (bool);
    function withdrawAll() external;
    function balance() external view returns (uint256);
    function balanceOf(address account) external view returns (uint256);
}