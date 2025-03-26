// SPDX-License-Identifier: MITaavaave
pragma solidity ^0.8.10;

import {IERC20} from "../../dependencies/openzeppelin/contracts/IERC20.sol";
import {IBeefyVault} from "../../interfaces/IBeefyVault.sol";
import {SafeERC20} from "../../dependencies/openzeppelin/contracts/SafeERC20.sol";
import {IPool} from "../../interfaces/IPool.sol";
import {BalancerPoolExit} from "../../added/BalancerExit.sol";
import {IBalancerVault} from "../../interfaces/IBalancerVault.sol";

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

contract AaveLiquidator {
    using SafeERC20 for IERC20;
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

    constructor(address _swapRouter, address _pool) {
        owner = msg.sender;
        odosSwapRouter = _swapRouter;
        POOL = IPool(_pool);
    }

    function encodeSwapParams(
        IOdosRouter.inputTokenInfo[] memory inputs,
        IOdosRouter.outputTokenInfo[] memory outputs,
        uint256 valueOutMin,
        bytes calldata pathDefinition,
        address executor,
        uint32 referralCode
    ) external pure returns (bytes memory) {
        return
            abi.encode(
                IOdosRouter.MultiSwapParams({
                    inputs: inputs,
                    outputs: outputs,
                    valueOutMin: valueOutMin,
                    pathDefinition: pathDefinition,
                    executor: executor,
                    referralCode: referralCode
                })
            );
    }

    function _beetsWithdraw(address vicunaVault) internal returns (address[] memory tokens) {
        IBeefyVault beefyVault = IBeefyVault(vicunaVault);
        IBeetsPool beetsPool = IBeetsPool(beefyVault.want());
        uint256 beforeWithdraw = IERC20(address(beetsPool)).balanceOf(address(this));
        IBalancerVault beetsVault = IBalancerVault(beetsPool.getVault());
        beefyVault.withdrawAll();

        uint256 withdrawAmount = IERC20(address(beetsPool)).balanceOf(address(this)) -
            beforeWithdraw;
        (tokens, , ) = beetsVault.getPoolTokens(beetsPool.getPoolId());
        uint256[] memory minAmountsOut = new uint256[](tokens.length); // slippage protected by MAX_PRICE_IMPACT

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

    /**
     * @dev Initie une liquidation via un flash loan
     * @param collateralAsset L'actif utilisé comme collatéral par la position à liquider
     * @param debtAsset L'actif emprunté par la position à liquider
     * @param user L'adresse de l'utilisateur à liquider
     * @param debtToCover Le montant de la dette à couvrir
     */
    function executeLiquidation(
        address collateralAsset,
        address debtAsset,
        address user,
        uint256 debtToCover,
        bytes calldata swapParams,
        MarketType marketType,
        IPool borrowPool
    ) external {
        bytes memory params = abi.encode(
            collateralAsset,
            debtAsset,
            user,
            debtToCover,
            swapParams,
            marketType,
            borrowPool
        );

        borrowPool.flashLoanSimple(address(this), debtAsset, debtToCover, params, 0);
    }

    enum MarketType {
        CLASSIC,
        ICHI_VAULT,
        BEETS_VAULT
    }

    function _beetsLiquidate(address collateralAsset, uint256, bytes memory swapParams) public {
        address[] memory tokens = _beetsWithdraw(collateralAsset);
        uint256 tokenLength = tokens.length;
        for (uint256 idx = 0; idx < tokenLength; idx++) {
            IERC20(tokens[idx]).approve(odosSwapRouter, type(uint256).max);
        }
        {
            (bool success, ) = odosSwapRouter.call(swapParams);
            require(success, "Echec du swap");
        }

        for (uint256 idx = 0; idx < tokenLength; idx++) {
            IERC20(tokens[idx]).approve(odosSwapRouter, 0);
        }
    }

    function _ichiLiquidate(address collateralAsset, uint256, bytes memory swapParams) public {
        IBeefyVaultV7 beefyVault = IBeefyVaultV7(collateralAsset);
        beefyVault.approve(collateralAsset, type(uint256).max);
        beefyVault.withdrawAll();
        IICHIVault ichiVault = IICHIVault(beefyVault.want());
        (uint256 amount0, uint256 amount1) = ichiVault.withdraw(
            ichiVault.balanceOf(address(this)),
            address(this)
        );
        ichiVault.token0().approve(odosSwapRouter, amount0);
        ichiVault.token1().approve(odosSwapRouter, amount1);

        // IOdosRouter.MultiSwapParams memory swapParamsStruct = abi.decode(swapParams, (IOdosRouter.MultiSwapParams));
        // swapParamsStruct.valueOutMin = swapParamsStruct.valueOutMin/2;
        // IOdosRouter(odosSwapRouter).swapMulti(
        //     swapParamsStruct.inputs,
        //     swapParamsStruct.outputs,
        //     swapParamsStruct.valueOutMin,
        //     swapParamsStruct.pathDefinition,
        //     swapParamsStruct.executor,
        //     swapParamsStruct.referralCode
        // );
        {
            (bool success, ) = odosSwapRouter.call(swapParams);
            require(success, "Echec du swap");
        }
    }

    function _classicLiquidate(
        address collateralAsset,
        uint256 amountToSwap,
        bytes memory swapParams
    ) internal {
        IERC20(collateralAsset).approve(odosSwapRouter, amountToSwap);
        {
            (bool success, ) = odosSwapRouter.call(swapParams);
            require(success, "Echec du swap");
        }
    }

    /**
     * @dev Callback appelé après réception du flash loan
     */
    function executeOperation(
        address asset,
        uint256 amount,
        uint256 premium,
        address,
        bytes calldata params
    ) external returns (bool) {
        // Décode les paramètres
        (
            address collateralAsset,
            address debtAsset,
            address user,
            uint256 debtToCover,
            bytes memory swapParams,
            MarketType marketType,
            address borrowPool
        ) = abi.decode(params, (address, address, address, uint256, bytes, MarketType, address));

        // 1. Approuve et exécute la liquidation
        IERC20(debtAsset).approve(address(POOL), debtToCover);
        POOL.liquidationCall(
            collateralAsset,
            debtAsset,
            user,
            debtToCover,
            false // Ne pas recevoir aToken
        );

        {
            // 2. Swap le collateral reçu contre le token de la dette
            uint256 amountToSwap = IERC20(collateralAsset).balanceOf(address(this));

            if (marketType == MarketType.ICHI_VAULT) {
                _ichiLiquidate(collateralAsset, amountToSwap, swapParams);
            } else if (marketType == MarketType.BEETS_VAULT) {
                _beetsLiquidate(collateralAsset, amountToSwap, swapParams);
            } else if (marketType == MarketType.CLASSIC) {
                _classicLiquidate(collateralAsset, amountToSwap, swapParams);
            }
        }
        // 3. Calcule le montant total à rembourser
        uint256 amountToRepay = amount + premium;

        // Vérifie que nous avons assez de tokens pour rembourser
        require(
            IERC20(asset).balanceOf(address(this)) >= amountToRepay,
            "Fonds insuffisants pour rembourser le flash loan"
        );

        // Approuve le remboursement
        IERC20(asset).approve(borrowPool, amountToRepay);

        return true;
    }

    /**
     * @dev Permet de récupérer les tokens restants après la liquidation
     * @param token L'adresse du token à récupérer
     */
    function rescueTokens(address token) external {
        require(msg.sender == owner, "Seul le proprietaire peut recuperer les tokens");
        uint256 balance = IERC20(token).balanceOf(address(this));
        IERC20(token).safeTransfer(owner, balance);
    }

    /**
     * @dev Permet de mettre à jour l'adresse du propriétaire
     * @param newOwner La nouvelle adresse propriétaire
     */
    function setOwner(address newOwner) external {
        require(msg.sender == owner, "Seul le proprietaire peut changer le proprietaire");
        require(newOwner != address(0), "Nouvelle adresse invalide");
        owner = newOwner;
    }
}
