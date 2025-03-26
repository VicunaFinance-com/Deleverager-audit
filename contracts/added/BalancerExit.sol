// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

import {IERC20} from "../dependencies/openzeppelin/contracts/IERC20.sol";
import {SafeERC20} from "../dependencies/openzeppelin/contracts/SafeERC20.sol";

// This program is free software: you can redistribute it and/or modify
// it under the terms of the GNU General Public License as published by
// the Free Software Foundation, either version 3 of the License, or
// (at your option) any later version.

// This program is distributed in the hope that it will be useful,
// but WITHOUT ANY WARRANTY; without even the implied warranty of
// MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
// GNU General Public License for more details.

// You should have received a copy of the GNU General Public License
// along with this program.  If not, see <http://www.gnu.org/licenses/>.

library StablePoolUserData {
    enum JoinKind {
        INIT,
        EXACT_TOKENS_IN_FOR_BPT_OUT,
        TOKEN_IN_FOR_EXACT_BPT_OUT,
        ALL_TOKENS_IN_FOR_EXACT_BPT_OUT
    }
    enum ExitKind {
        EXACT_BPT_IN_FOR_ONE_TOKEN_OUT,
        BPT_IN_FOR_EXACT_TOKENS_OUT,
        EXACT_BPT_IN_FOR_ALL_TOKENS_OUT
    }

    function joinKind(bytes memory self) internal pure returns (JoinKind) {
        return abi.decode(self, (JoinKind));
    }

    function exitKind(bytes memory self) internal pure returns (ExitKind) {
        return abi.decode(self, (ExitKind));
    }

    // Joins

    function initialAmountsIn(
        bytes memory self
    ) internal pure returns (uint256[] memory amountsIn) {
        (, amountsIn) = abi.decode(self, (JoinKind, uint256[]));
    }

    function exactTokensInForBptOut(
        bytes memory self
    ) internal pure returns (uint256[] memory amountsIn, uint256 minBPTAmountOut) {
        (, amountsIn, minBPTAmountOut) = abi.decode(self, (JoinKind, uint256[], uint256));
    }

    function tokenInForExactBptOut(
        bytes memory self
    ) internal pure returns (uint256 bptAmountOut, uint256 tokenIndex) {
        (, bptAmountOut, tokenIndex) = abi.decode(self, (JoinKind, uint256, uint256));
    }

    function allTokensInForExactBptOut(
        bytes memory self
    ) internal pure returns (uint256 bptAmountOut) {
        (, bptAmountOut) = abi.decode(self, (JoinKind, uint256));
    }

    // Exits

    function exactBptInForTokenOut(
        bytes memory self
    ) internal pure returns (uint256 bptAmountIn, uint256 tokenIndex) {
        (, bptAmountIn, tokenIndex) = abi.decode(self, (ExitKind, uint256, uint256));
    }

    function exactBptInForTokensOut(bytes memory self) internal pure returns (uint256 bptAmountIn) {
        (, bptAmountIn) = abi.decode(self, (ExitKind, uint256));
    }

    function bptInForExactTokensOut(
        bytes memory self
    ) internal pure returns (uint256[] memory amountsOut, uint256 maxBPTAmountIn) {
        (, amountsOut, maxBPTAmountIn) = abi.decode(self, (ExitKind, uint256[], uint256));
    }
}

interface IVault {
    enum ExitKind {
        EXACT_BPT_IN_FOR_ONE_TOKEN_OUT,
        BPT_IN_FOR_EXACT_TOKENS_OUT,
        EXACT_BPT_IN_FOR_ALL_TOKENS_OUT
    }

    function getPoolTokens(
        bytes32 poolId
    )
        external
        view
        returns (IERC20[] memory tokens, uint256[] memory balances, uint256 lastChangeBlock);

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

    function setRelayerApproval(address sender, address relayer, bool approved) external;
}

library BalancerPoolExit {
    using SafeERC20 for IERC20;

    using StablePoolUserData for bytes;


    function exitBalancerPool(address vault, bytes32 poolId, uint256 bptAmountIn, address recipient) internal returns (address[] memory) {
        // Step 1: Ensure the relayer is approved (call this once before any exits)
        // vault.setRelayerApproval(address(this), address(vault), true);

        // Step 2: Get pool tokens in the correct order from the Vault
        (IERC20[] memory poolTokens, , ) = IVault(vault).getPoolTokens(poolId);

        // Step 3: Convert IERC20[] to address[] for the assets parameter
        address[] memory assets = new address[](poolTokens.length);
        for (uint256 i = 0; i < poolTokens.length; i++) {
            assets[i] = address(poolTokens[i]);
        }

        // Step 4: Create minAmountsOut array
        // For safety, you can set these to a percentage (e.g., 95%) of the expected amounts
        // For simplicity, we're using 0 here, but in production you should add slippage protection
        uint256[] memory minAmountsOut = new uint256[](assets.length);

        // Optional: Calculate expected output amounts and set minimum amounts with slippage
        // The exact method depends on pool type, but here's an approximation
        /*
    uint256 totalBptSupply = IERC20(address(bytes20(poolId))).totalSupply();
    for (uint256 i = 0; i < assets.length; i++) {
        // Expected amount is proportional share of the pool's token balance
        uint256 expectedAmount = (balances[i] * bptAmountIn) / totalBptSupply;
        // Apply slippage tolerance (e.g., 2%)
        minAmountsOut[i] = (expectedAmount * 98) / 100;
    }
    */

        // Step 5: Approve the Vault to spend the BPT tokens
        address poolAddress = address(bytes20(poolId));
        IERC20(poolAddress).safeTransferFrom(msg.sender, address(this), bptAmountIn);
        IERC20(poolAddress).approve(address(vault), bptAmountIn);

        // Step 6: Encode userData for EXACT_BPT_IN_FOR_TOKENS_OUT (type 1)
        bytes memory userData = abi.encode(
            IVault.ExitKind.EXACT_BPT_IN_FOR_ALL_TOKENS_OUT,
            bptAmountIn
        );

        // Step 7: Create the exit request
        IVault.ExitPoolRequest memory request = IVault.ExitPoolRequest({
            assets: assets,
            minAmountsOut: minAmountsOut,
            userData: userData,
            toInternalBalance: false // Send tokens directly to recipient
        });

        // Step 8: Execute the exit
        IVault(vault).exitPool(
            poolId,
            address(this), // Sender (this contract)
            recipient, // Recipient of the tokens
            request
        );
        return assets;
    }

    /**
     * @notice Exit a Balancer pool by burning BPT and receiving all underlying tokens
     * @param poolId The id of the pool to exit
     * @param bptAmountIn The amount of BPT to burn
     * @param minAmountsOut Minimum amounts of each token to receive
     * @param recipient Address to receive the tokens
     */
    // function exitPool(
    //     bytes32 poolId,
    //     uint256 bptAmountIn,
    //     address[] calldata tokens,
    //     uint256[] calldata minAmountsOut,
    //     address recipient
    // ) external {
    //     // Approve vault to spend BPT tokens
    //     address poolAddress = address(bytes20(poolId)); // Extract pool address from poolId
    //     IERC20(poolAddress).approve(address(vault), bptAmountIn);
    //     vault.setRelayerApproval(
    //         address(this), // sender (your contract)
    //         address(vault), // relayer (the Vault itself)
    //         true // approved
    //     );
    //     // Encode userData for exact BPT in for tokens out
    //     bytes memory userData = abi.encode(
    //         IVault.ExitKind.EXACT_BPT_IN_FOR_ALL_TOKENS_OUT,
    //         minAmountsOut,
    //         bptAmountIn
    //     );
    //
    //     // Create exit request
    //     IVault.ExitPoolRequest memory request = IVault.ExitPoolRequest({
    //         assets: tokens,
    //         minAmountsOut: minAmountsOut,
    //         userData: userData,
    //         toInternalBalance: false // We want tokens sent directly to the recipient
    //     });
    //
    //     // Execute exit
    //     vault.exitPool(
    //         poolId,
    //         address(this), // sender (this contract)
    //         recipient, // recipient of the tokens
    //         request
    //     );
    // }

    /**
     * @notice Exit a Balancer pool by burning BPT and receiving a single token
     * @param poolId The id of the pool to exit
     * @param bptAmountIn The amount of BPT to burn
     * @param tokenIndex Index of the token to receive
     * @param minAmountOut Minimum amount of the token to receive
     * @param recipient Address to receive the token
     */
    // function exitPoolForSingleToken(
    //     bytes32 poolId,
    //     uint256 bptAmountIn,
    //     address[] calldata tokens,
    //     uint256 tokenIndex,
    //     uint256 minAmountOut,
    //     address recipient
    // ) external {
    //     // Approve vault to spend BPT tokens
    //     address poolAddress = address(bytes20(poolId)); // Extract pool address from poolId
    //     IERC20(poolAddress).approve(address(vault), bptAmountIn);
    //
    //     // Encode userData for exact BPT in for one token out
    //     bytes memory userData = abi.encode(
    //         uint8(IVault.ExitKind.EXACT_BPT_IN_FOR_ONE_TOKEN_OUT),
    //         bptAmountIn,
    //         tokenIndex
    //     );
    //
    //     // Create minAmountsOut array with minimum amount only for the selected token
    //     uint256[] memory minAmountsOut = new uint256[](tokens.length);
    //     minAmountsOut[tokenIndex] = minAmountOut;
    //
    //     // Create exit request
    //     IVault.ExitPoolRequest memory request = IVault.ExitPoolRequest({
    //         assets: tokens,
    //         minAmountsOut: minAmountsOut,
    //         userData: userData,
    //         toInternalBalance: false
    //     });
    //
    //     // Execute exit
    //     vault.exitPool(poolId, address(this), recipient, request);
    // }
}
