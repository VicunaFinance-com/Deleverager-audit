pragma solidity ^0.8.0;



interface IBeetsPool {
    function getPoolId() external view returns (bytes32);

    function getRate() external view returns (uint256);

    function getVault() external view returns (address);

    function getActualSupply() external view returns (uint256);

    function totalSupply() external view returns (uint256);

    function balanceOf(address account) external view returns (uint256);
    function transfer(address recipient, uint256 amount) external returns (bool);
}