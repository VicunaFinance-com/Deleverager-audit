pragma solidity ^0.8.0;

interface IBeetsVaultOracle {
    function getTotalTokensInPool()
        external
        view
        returns (uint256[] memory values, address[] memory tokens);
    function latestAnswer() external view returns (int256);
}
