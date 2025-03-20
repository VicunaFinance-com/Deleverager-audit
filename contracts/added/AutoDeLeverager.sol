// SPDX-License-Identifier: BUSL-1.1
pragma solidity ^0.8.10;

import {AggregatorInterface} from "../dependencies/chainlink/AggregatorInterface.sol";
import {IERC20} from "../dependencies/openzeppelin/contracts/IERC20.sol";
import {SafeERC20} from "../dependencies/openzeppelin/contracts/SafeERC20.sol";
import {IPyth, Price} from "../interfaces/IPyth.sol";
import {Ownable} from "../dependencies/openzeppelin/contracts/Ownable.sol";
import {DataTypes} from "../protocol/libraries/types/DataTypes.sol";
import {IPeggedOracle} from "../interfaces/IPeggedOracle.sol";
import {IICHIVault} from "../interfaces/IICHIVault.sol";
import {IPool} from "../interfaces/IPool.sol";
import {IBeefyVault} from "../interfaces/IBeefyVault.sol";
import {IPoolDataProvider} from "../interfaces/IPoolDataProvider.sol";
import {ReserveConfiguration} from "../protocol/libraries/configuration/ReserveConfiguration.sol";
import {UserConfiguration} from "../protocol/libraries/configuration/UserConfiguration.sol";
import {IAaveOracle} from "../interfaces/IAaveOracle.sol";

import {Pausable} from "../dependencies/openzeppelin/contracts/Pausable.sol";

import {IAToken} from "../interfaces/IAToken.sol";

/**
 * @title Autoleverager
 * @author Your Name
 * @notice This contract automates leveraged positions in AAVE markets using ICHI vaults and Beefy vaults
 * @dev Uses flash loans to achieve leverage and handles the complete flow of leverage deposit
 */
contract AutoDeLeverager is Ownable, Pausable {
    using ReserveConfiguration for DataTypes.ReserveConfigurationMap;
    using UserConfiguration for DataTypes.UserConfigurationMap;
    using SafeERC20 for IERC20;

    /// @notice Router used for token swaps
    address public odosRouter;

    /// @notice Address that receives fees
    address public feeReceiver;

    /// @notice Fee percentage (10000 = 100%)
    uint256 public fee;

    /// @notice Main pool for supply and borrow operations
    IPool public pool;

    /// @notice Pool used for flash loans
    IPool public borrowPool;

    IAaveOracle public oracle;

    address[] public supportedAssets;
    uint256 public MAX_PRICE_IMPACT;

    /// @notice Emitted when a leveraged deposit is completed
    event LeverageDeposited(
        address indexed user,
        address withdrawAsset,
        address borrowAsset,
        uint256 withdrawAmount,
        address ichiVault,
        address vicunaVault
    );

    /// @notice Emitted when the fee percentage is updated
    event FeeUpdated(uint256 oldFee, uint256 newFee);

    /// @notice Emitted when a contract parameter is updated
    event ParameterUpdated(string paramName, address oldValue, address newValue);

    /// @notice Emitted when tokens are rescued in an emergency
    event TokensRescued(address indexed token, address indexed recipient, uint256 amount);

    event ValueOfTokenInContract(uint256 value);

    /**
     * @notice Constructor to initialize the Autoleverager contract
     * @param _odosRouter Address of the ODOS router for swaps
     * @param _pool Address of the main pool for supply/borrow
     * @param _borrowPool Address of the pool for flash loans
     * @param _feeReceiver Address that will receive fees
     */
    constructor(
        address _odosRouter,
        address _pool,
        address _borrowPool,
        address _feeReceiver,
        address _oracle
    ) {
        odosRouter = _odosRouter;
        pool = IPool(_pool);
        borrowPool = IPool(_borrowPool);
        feeReceiver = _feeReceiver;
        oracle = IAaveOracle(_oracle);
    }

    /**
     * @notice Sets the fee percentage
     * @param _fee New fee percentage (10000 = 100%)
     */
    function setFee(uint256 _fee) external onlyOwner {
        require(_fee <= 10000, "Fee too high");
        uint256 oldFee = fee;
        fee = _fee;
        emit FeeUpdated(oldFee, _fee);
    }

    function addSupportedAsset(address asset) external onlyOwner {
        supportedAssets.push(asset);
    }

    function removeSupportedAsset(address asset) external onlyOwner {
        for (uint256 i = 0; i < supportedAssets.length; i++) {
            if (supportedAssets[i] == asset) {
                supportedAssets[i] = supportedAssets[supportedAssets.length - 1];
                supportedAssets.pop();
                break;
            }
        }
    }

    function setMaxPriceImpact(uint256 _maxPriceImpact) external onlyOwner {
        MAX_PRICE_IMPACT = _maxPriceImpact;
    }

    /**
     * @notice Sets the ODOS router address
     * @param _odosRouter New router address
     */
    function setOdosRouter(address _odosRouter) external onlyOwner {
        require(_odosRouter != address(0), "Invalid address");
        address oldRouter = odosRouter;
        odosRouter = _odosRouter;
        emit ParameterUpdated("odosRouter", oldRouter, _odosRouter);
    }

    /**
     * @notice Sets the main pool address
     * @param _pool New pool address
     */
    function setPool(address _pool) external onlyOwner {
        require(_pool != address(0), "Invalid address");
        address oldPool = address(pool);
        pool = IPool(_pool);
        emit ParameterUpdated("pool", oldPool, _pool);
    }

    /**
     * @notice Sets the borrow pool address used for flash loans
     * @param _borrowPool New borrow pool address
     */
    function setBorrowPool(address _borrowPool) external onlyOwner {
        require(_borrowPool != address(0), "Invalid address");
        address oldBorrowPool = address(borrowPool);
        borrowPool = IPool(_borrowPool);
        emit ParameterUpdated("borrowPool", oldBorrowPool, _borrowPool);
    }

    /**
     * @notice Sets the fee receiver address
     * @param _feeReceiver New fee receiver address
     */
    function setFeeReceiver(address _feeReceiver) external onlyOwner {
        require(_feeReceiver != address(0), "Invalid address");
        address oldFeeReceiver = feeReceiver;
        feeReceiver = _feeReceiver;
        emit ParameterUpdated("feeReceiver", oldFeeReceiver, _feeReceiver);
    }

    function pause() external onlyOwner {
        _pause();
    }

    function unpause() external onlyOwner {
        _unpause();
    }

    /**
     * @notice Helper function to get token decimals
     * @param token Address of the token
     * @return uint8 Token decimals
     */
    function getDecimals(address token) internal view returns (uint8) {
        (bool success, bytes memory data) = token.staticcall(abi.encodeWithSignature("decimals()"));
        require(success, "Failed to get decimals");
        return abi.decode(data, (uint8));
    }

    /**
     * @notice Converts amount from one token's decimals to another
     * @param amount Amount to convert
     * @param fromDecimals Source token decimals
     * @param toDecimals Target token decimals
     * @return Converted amount
     */
    function convertDecimals(
        uint256 amount,
        uint8 fromDecimals,
        uint8 toDecimals
    ) internal pure returns (uint256) {
        if (fromDecimals == toDecimals) {
            return amount;
        } else if (fromDecimals > toDecimals) {
            return amount / (10 ** (fromDecimals - toDecimals));
        } else {
            return amount * (10 ** (toDecimals - fromDecimals));
        }
    }

    struct TokenAmount {
        IERC20 token;
        uint256 amount;
    }
    struct WithdrawData {
        inputWithdrawData inputData;
        address sender;
        address withdrawAsset;
        TokenAmount[] initialBalances;
    }

    struct inputWithdrawData {
        address withdrawAssetAToken;
        address borrowAsset;
        uint256 withdrawAmount;
        uint256 repayAmount;
        address vicunaVault;
        bytes swapParams;
    }

    function _extractTokenData(address asset) public view returns (uint256 baseLTVasCollateral) {
        DataTypes.ReserveData memory baseData = pool.getReserveData(asset);
        DataTypes.ReserveConfigurationMap memory reserveConfigurationMap = baseData.configuration;
        (baseLTVasCollateral, , , , , ) = reserveConfigurationMap.getParams();
    }

    function computeNeedToFlash(
        address borrowedToken,
        address suppliedToken,
        uint256 suppliedAmountToWithdraw
    ) public view returns (uint256) {
        uint256 collateralFactor = _extractTokenData(suppliedToken);
        uint256 borrowAssetPrice = oracle.getAssetPrice(borrowedToken);
        uint256 suppliedAssetPrice = oracle.getAssetPrice(suppliedToken);
        uint256 neededToFlash = (suppliedAmountToWithdraw * suppliedAssetPrice * collateralFactor) /
            borrowAssetPrice /
            1e4;
        return
            convertDecimals(
                neededToFlash,
                IERC20(suppliedToken).decimals(),
                IERC20(borrowedToken).decimals()
            );
    }

    function computeAtokenAmount(
        address borrowedToken,
        address suppliedToken,
        uint256 borrowedAmountToRepay
    ) public view returns (uint256) {
        uint256 collateralFactor = _extractTokenData(suppliedToken);
        uint256 borrowAssetPrice = oracle.getAssetPrice(borrowedToken);
        uint256 suppliedAssetPrice = oracle.getAssetPrice(suppliedToken);
        uint256 neededAToken = (borrowedAmountToRepay * borrowAssetPrice * 1e4) /
            (suppliedAssetPrice * collateralFactor);
        return
            convertDecimals(
                neededAToken,
                IERC20(borrowedToken).decimals(),
                IERC20(suppliedToken).decimals()
            );
    }

    function _checkValueOfSupportedAssetInContract() internal view returns (uint256) {
        uint256 totalValue;
        for (uint256 i = 0; i < supportedAssets.length; i++) {
            uint256 bal = IERC20(supportedAssets[i]).balanceOf(address(this));
            uint256 price = oracle.getAssetPrice(supportedAssets[i]);
            bal = convertDecimals(bal, IERC20(supportedAssets[i]).decimals(), 18);
            totalValue += (bal * price) / 1e18;
        }
        return totalValue;
    }

    /**
     * @notice Creates a leveraged position using flash loans
     */
    function leverageWithdraw(inputWithdrawData calldata inputParameters) external whenNotPaused {
        WithdrawData memory withdrawParams;
        withdrawParams.sender = msg.sender;
        withdrawParams.inputData = inputParameters;

        withdrawParams.withdrawAsset = IAToken(inputParameters.withdrawAssetAToken)
            .UNDERLYING_ASSET_ADDRESS();

        bool isSimpleToken;
        IBeefyVault beefyVault = IBeefyVault(inputParameters.vicunaVault);
        try beefyVault.want() returns (address) {
            isSimpleToken = false;
        } catch Error(string memory) {
            isSimpleToken = true;
        }
        withdrawParams.initialBalances = new TokenAmount[](isSimpleToken ? 2 : 3);
        withdrawParams.initialBalances[0] = TokenAmount(
            IERC20(inputParameters.borrowAsset),
            IERC20(inputParameters.borrowAsset).balanceOf(address(this))
        );

        if (isSimpleToken) {
            withdrawParams.initialBalances[1] = TokenAmount(
                IERC20(withdrawParams.withdrawAsset),
                IERC20(withdrawParams.withdrawAsset).balanceOf(address(this))
            );
        } else {
            IICHIVault ichiVault = IICHIVault(beefyVault.want());

            if (inputParameters.borrowAsset != ichiVault.token0()) {
                withdrawParams.initialBalances[1] = TokenAmount(
                    IERC20(ichiVault.token0()),
                    IERC20(ichiVault.token0()).balanceOf(address(this))
                );
            }
            if (inputParameters.borrowAsset != ichiVault.token1()) {
                withdrawParams.initialBalances[2] = TokenAmount(
                    IERC20(ichiVault.token1()),
                    IERC20(ichiVault.token1()).balanceOf(address(this))
                );
            }
        }

        bytes memory params = abi.encode(withdrawParams);

        // Borrow the asset needed to deposit in the vault
        address[] memory assets = new address[](1);
        assets[0] = inputParameters.borrowAsset;
        uint256[] memory amounts = new uint256[](1);
        amounts[0] = inputParameters.repayAmount;
        uint256[] memory modes = new uint256[](1);
        modes[0] = 0;
        borrowPool.flashLoan(address(this), assets, amounts, modes, address(this), params, 0);
    }

    /**
     * @notice Flash loan callback function
     * @param assets Assets received from flash loan
     * @param amounts Amounts of flash loaned assets
     * @param initiator Address that initiated the flash loan
     * @param params Encoded parameters
     * @return success True if the operation was successful
     */
    function executeOperation(
        address[] calldata assets,
        uint256[] calldata amounts,
        uint256[] calldata,
        address initiator,
        bytes calldata params
    ) external whenNotPaused returns (bool) {
        require(msg.sender == address(borrowPool), "Only borrowPool can call this function");
        require(initiator == address(this), "Only this contract can initiate the flash loan");

        WithdrawData memory withdrawData = abi.decode(params, (WithdrawData));
        address flashLoanAsset = assets[0];
        uint256 flashLoanAmount = amounts[0];

        IERC20(flashLoanAsset).approve(address(pool), flashLoanAmount);
        pool.repay(flashLoanAsset, flashLoanAmount, 2, withdrawData.sender);

        IERC20(withdrawData.inputData.withdrawAssetAToken).safeTransferFrom(
            withdrawData.sender,
            address(this),
            withdrawData.inputData.withdrawAmount
        );
        pool.withdraw(
            withdrawData.withdrawAsset,
            withdrawData.inputData.withdrawAmount,
            address(this)
        );

        // Withdraw from Beefy vault
        bool isSimpleToken;
        IBeefyVault beefyVault = IBeefyVault(withdrawData.inputData.vicunaVault);
        try beefyVault.want() returns (address) {
            isSimpleToken = false;
        } catch Error(string memory) {
            isSimpleToken = true;
        }
        if (!isSimpleToken) {
            IICHIVault ichiVault = IICHIVault(beefyVault.want());
            uint256 beforeWithdraw = IERC20(address(ichiVault)).balanceOf(address(this));
            beefyVault.withdrawAll();
            uint256 ichiAmount = IERC20(address(ichiVault)).balanceOf(address(this)) -
                beforeWithdraw;

            // Withdraw from ICHI vault
            IICHIVault(ichiVault).withdraw(ichiAmount, address(this));
        }

        // Swap to borrow asset
        if (withdrawData.inputData.swapParams.length > 0) {
            if (isSimpleToken) {
                IERC20(withdrawData.withdrawAsset).approve(odosRouter, type(uint256).max);
            } else {
                IICHIVault ichiVault = IICHIVault(beefyVault.want());
                IERC20(ichiVault.token0()).approve(odosRouter, type(uint256).max);
                IERC20(ichiVault.token1()).approve(odosRouter, type(uint256).max);
            }
            // Check value of assets received before swapping
            uint256 totalValueBeforeSwap = _checkValueOfSupportedAssetInContract();
            emit ValueOfTokenInContract(totalValueBeforeSwap);
            (bool success, ) = odosRouter.call(withdrawData.inputData.swapParams);
            require(success, "Swap failed");
            uint256 totalValueAfterSwap = _checkValueOfSupportedAssetInContract();
            emit ValueOfTokenInContract(totalValueAfterSwap);
            require(
                totalValueAfterSwap >= totalValueBeforeSwap ||
                    totalValueBeforeSwap - totalValueAfterSwap <=
                    (totalValueBeforeSwap * MAX_PRICE_IMPACT) / 10000,
                "Price impact too high"
            );
        }

        IERC20(withdrawData.inputData.borrowAsset).approve(address(borrowPool), flashLoanAmount);

        {
            uint256 previousBalancesLength = withdrawData.initialBalances.length;

            for (uint256 idx = 0; idx < previousBalancesLength; idx++) {
                TokenAmount memory tokenAmount = withdrawData.initialBalances[idx];
                if (address(tokenAmount.token) == address(0)) {
                    continue;
                }
                uint256 remainingAmount = tokenAmount.token.balanceOf(address(this)) -
                    (
                        address(tokenAmount.token) == withdrawData.inputData.borrowAsset
                            ? flashLoanAmount
                            : 0
                    );

                require(remainingAmount >= tokenAmount.amount, "IMBALANCE");
                if (remainingAmount > tokenAmount.amount) {
                    uint256 feeAmount;
                    if (fee > 0) {
                        feeAmount = ((remainingAmount - tokenAmount.amount) * fee) / 10000;
                        tokenAmount.token.safeTransfer(feeReceiver, feeAmount);
                    }
                    tokenAmount.token.safeTransfer(
                        withdrawData.sender,
                        remainingAmount - tokenAmount.amount - feeAmount
                    );
                }
            }
        }

        return true;
    }

    /**
     * @notice Rescues tokens accidentally sent to the contract
     * @param token Address of the token to rescue
     * @param to Address to send the tokens to
     * @param amount Amount of tokens to rescue
     */
    function rescueTokens(address token, address to, uint256 amount) external onlyOwner {
        require(to != address(0), "Cannot send to zero address");

        IERC20(token).safeTransfer(to, amount);

        emit TokensRescued(token, to, amount);
    }

    /**
     * @notice Rescues ETH accidentally sent to the contract
     * @param to Address to send the ETH to
     * @param amount Amount of ETH to rescue
     */
    function rescueETH(address payable to, uint256 amount) external onlyOwner {
        require(to != address(0), "Cannot send to zero address");
        require(address(this).balance >= amount, "Insufficient ETH balance");

        (bool success, ) = to.call{value: amount}("");
        require(success, "ETH transfer failed");

        emit TokensRescued(address(0), to, amount);
    }

    /**
     * @notice Allows the contract to receive ETH
     */
    receive() external payable {}
}
