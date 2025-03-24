// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

interface IICHIVault {
    /**
     * @notice Gets total supply of LP tokens
     * @return Total supply of LP tokens
     */
    function totalSupply() external view returns (uint256);

    /**
     * @notice Gets the address of token0
     * @return Address of token0
     */
    function token0() external view returns (address);

    /**
     * @notice Gets the address of token1
     * @return Address of token1
     */
    function token1() external view returns (address);

    /**
     * @notice Calculates total quantity of token0 and token1 in both positions (and unused in the ICHIVault)
     * @return total0 Quantity of token0 in both positions (and unused in the ICHIVault)
     * @return total1 Quantity of token1 in both positions (and unused in the ICHIVault)
     */
    function getTotalAmounts() external view returns (uint256 total0, uint256 total1);

    function allowToken0() external view returns(bool);
    function allowToken1() external view returns(bool);
    function deposit(uint256 amount0, uint256 amount1, address to) external returns(uint256 shares);
    function withdraw(uint256 shares, address to) external returns(uint256 amount0, uint256 amount1);
}