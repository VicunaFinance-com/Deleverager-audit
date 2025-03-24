// SPDX-License-Identifier: AGPL-3.0
pragma solidity ^0.8.0;




interface IBalancerVault {


    struct JoinPoolRequest {
    address[] assets;
    uint256[] maxAmountsIn;
    bytes userData;
    bool fromInternalBalance;
    }

    function joinPool(bytes32 poolId, address sender, address recipient, JoinPoolRequest memory request) external;
    function getPoolTokens(bytes32 poolId) 
    external view 
    returns (
        address[] memory tokens,
        uint256[] memory balances,
        uint256 lastChangeBlock
    );
    function queryJoin(
        bytes32 poolId,
        address sender,
        address recipient,
        JoinPoolRequest memory request
    ) external view returns (uint256 bptOut, uint256[] memory amountsIn);

    function getPool(bytes32 poolId) external view returns (address, uint8);

    struct ExitPoolRequest {
        address[] assets;
        uint256[] minAmountsOut;
        bytes userData;
        bool toInternalBalance;
    }
    function exitPool(
        bytes32 poolId,
        address sender,
        address recipient,
        ExitPoolRequest calldata request
    ) external;
}
