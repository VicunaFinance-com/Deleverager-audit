// SPDX-License-Identifier: BUSL-1.1
pragma solidity ^0.8.10;

import {AggregatorInterface} from "../dependencies/chainlink/AggregatorInterface.sol";
import {IERC20} from "../dependencies/openzeppelin/contracts/IERC20.sol";
import {SafeERC20} from "../dependencies/openzeppelin/contracts/SafeERC20.sol";
import {IPyth, Price} from "../interfaces/IPyth.sol";
import {Ownable} from "../dependencies/openzeppelin/contracts/Ownable.sol";
import {IPeggedOracle} from "../interfaces/IPeggedOracle.sol";
import {IICHIVault} from "../interfaces/IICHIVault.sol";
import {IPool} from "../interfaces/IPool.sol";
import {IBeefyVault} from "../interfaces/IBeefyVault.sol";

import {Pausable} from "../dependencies/openzeppelin/contracts/Pausable.sol";

/**
 * @title Autoleverager
 * @author Vicuna Finance
 * @notice This contract automates leveraged positions in AAVE markets using ICHI vaults and Beefy vaults
 * @dev Uses flash loans to achieve leverage and handles the complete flow of leverage deposit
 */
contract AutoLeverager is Ownable, Pausable {
    using SafeERC20 for IERC20;

    /// @notice Router used for token swaps
    address public odosRouter;
    bytes4 public constant swapCompactSelector = 0x83bd37f9;

    /// @notice Address that receives fees
    address public feeReceiver;

    /// @notice Fee percentage (10000 = 100%)
    uint256 public fee;

    /// @notice Main pool for supply and borrow operations
    IPool public pool;

    /// @notice Pool used for flash loans
    IPool public borrowPool;

    uint256 public DENOMINATOR = 10000;

    /// @notice Emitted when a leveraged deposit is completed
    event LeverageDeposited(
        address indexed user,
        address depositAsset,
        address borrowAsset,
        uint256 initialAmount,
        address ichiVault,
        address vicunaVault
    );

    /// @notice Emitted when the fee percentage is updated
    event FeeUpdated(uint256 oldFee, uint256 newFee);

    /// @notice Emitted when a contract parameter is updated
    event ParameterUpdated(string paramName, address oldValue, address newValue);

    /// @notice Emitted when tokens are rescued in an emergency
    event TokensRescued(address indexed token, address indexed recipient, uint256 amount);
    
    /**
     * @notice Constructor to initialize the Autoleverager contract
     * @param _odosRouter Address of the ODOS router for swaps
     * @param _pool Address of the main pool for supply/borrow
     * @param _borrowPool Address of the pool for flash loans
     * @param _feeReceiver Address that will receive fees
     */
    constructor(address _odosRouter, address _pool, address _borrowPool, address _feeReceiver) {
        _setOdosRouter(_odosRouter);
        setPool(_pool);
        setBorrowPool(_borrowPool);
        setFeeReceiver(_feeReceiver);
    }

    /**
     * @notice Sets the fee percentage
     * @param _fee New fee percentage (10000 = 100%)
     */
    function setFee(uint256 _fee) external onlyOwner {
        require(_fee <= 500, "Fee too high");
        uint256 oldFee = fee;
        fee = _fee;
        emit FeeUpdated(oldFee, _fee);
    }

    function pause() external onlyOwner {
        _pause();
    }

    function unpause() external onlyOwner {
        _unpause();
    }

    /**
     * @notice Sets the ODOS router address
     * @param _odosRouter New router address
     */
    function _setOdosRouter(address _odosRouter) internal {
        require(_odosRouter != address(0), "Invalid address");
        address oldRouter = odosRouter;
        odosRouter = _odosRouter;
        emit ParameterUpdated("odosRouter", oldRouter, _odosRouter);
    }

    /**
     * @notice Sets the main pool address
     * @param _pool New pool address
     */
    function setPool(address _pool) public onlyOwner {
        require(_pool != address(0), "Invalid address");
        address oldPool = address(pool);
        pool = IPool(_pool);
        emit ParameterUpdated("pool", oldPool, _pool);
    }

    /**
     * @notice Sets the borrow pool address used for flash loans
     * @param _borrowPool New borrow pool address
     */
    function setBorrowPool(address _borrowPool) public onlyOwner {
        require(_borrowPool != address(0), "Invalid address");
        address oldBorrowPool = address(borrowPool);
        borrowPool = IPool(_borrowPool);
        emit ParameterUpdated("borrowPool", oldBorrowPool, _borrowPool);
    }

    /**
     * @notice Sets the fee receiver address
     * @param _feeReceiver New fee receiver address
     */
    function setFeeReceiver(address _feeReceiver) public onlyOwner {
        require(_feeReceiver != address(0), "Invalid address");
        address oldFeeReceiver = feeReceiver;
        feeReceiver = _feeReceiver;
        emit ParameterUpdated("feeReceiver", oldFeeReceiver, _feeReceiver);
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


    struct DepositData {
        InputDepositData inputData;
        uint256 initialAmountAfterFee;
        address sender;
        address vaultDepositAsset;
    }
    struct InputDepositData {
        address depositAsset;
        address borrowAsset;
        uint256 initialAmount;
        uint256 borrowAmount;
        address vicunaVault;
        bytes swapParams;
    }

    /**
     * @notice Creates a leveraged position using flash loans
     */
    function leverageDeposit(InputDepositData calldata inputParameters) external whenNotPaused {
        DepositData memory depositParams;
        depositParams.sender = msg.sender;
        depositParams.inputData = inputParameters;

        address ichiVault = IBeefyVault(inputParameters.vicunaVault).want();
        {
            address token0 = IICHIVault(ichiVault).token0();
            address token1 = IICHIVault(ichiVault).token1();

            depositParams.vaultDepositAsset = IICHIVault(ichiVault).allowToken0() ? token0 : token1;

            require(
                inputParameters.depositAsset == depositParams.vaultDepositAsset ||
                    inputParameters.depositAsset == inputParameters.borrowAsset ||
                    depositParams.vaultDepositAsset == inputParameters.borrowAsset,
                "Invalid deposit/borrow asset"
            );

            require(inputParameters.borrowAmount > 0, "BorrowAmount should be positive");
        }

        IERC20(inputParameters.depositAsset).safeTransferFrom(
            msg.sender,
            address(this),
            inputParameters.initialAmount
        );

        // Calculate and transfer fee
        uint256 feeAmount = (inputParameters.initialAmount * fee) / DENOMINATOR;
        if (feeAmount > 0) {
            IERC20(inputParameters.depositAsset).safeTransfer(feeReceiver, feeAmount);
        }

        depositParams.initialAmountAfterFee = inputParameters.initialAmount - feeAmount;
        uint256 neededToFlash = inputParameters.borrowAmount;

        bytes memory params = abi.encode(depositParams);

        // Borrow the asset needed to deposit in the vault
        address[] memory assets = new address[](1);
        assets[0] = inputParameters.borrowAsset;
        uint256[] memory amounts = new uint256[](1);
        amounts[0] = neededToFlash;
        uint256[] memory modes = new uint256[](1);
        modes[0] = 0;
        borrowPool.flashLoan(address(this), assets, amounts, modes, address(this), params, 0);

        emit LeverageDeposited(
            msg.sender,
            inputParameters.depositAsset,
            inputParameters.borrowAsset,
            inputParameters.initialAmount,
            ichiVault,
            inputParameters.vicunaVault
        );
    }

    /**
     * @notice Flash loan callback function
     * @param assets Assets received from flash loan
     * @param amounts Amounts of flash loaned assets
     * @param params Encoded parameters
     * @return success True if the operation was successful
     */
    function executeOperation(
        address[] calldata assets,
        uint256[] calldata amounts,
        uint256[] calldata,
        address initiator,
        bytes calldata params
    ) external returns (bool) {
        require(msg.sender == address(borrowPool), "Only borrowPool can call this function");
        require(initiator == address(this), "Flash loan can only be initiated by this contract");

        DepositData memory depositData = abi.decode(params, (DepositData));
        address vaultDepositAsset = depositData.vaultDepositAsset;
        address flashLoanAsset = assets[0];
        uint256 flashLoanAmount = amounts[0];
        // uint256 premium = premiums[0];

        uint256 depositAmount;
        if (depositData.inputData.depositAsset == vaultDepositAsset) {
            // If depositAsset is the same as vaultDepositAsset, use both the flash loan amount and user deposit
            depositAmount += depositData.initialAmountAfterFee;
        }
        if (vaultDepositAsset == flashLoanAsset) {
            // If depositAsset is different from vaultDepositAsset, use only the flash loan amount
            depositAmount += flashLoanAmount;
        }

        uint256 swapAmountoutput;
        if (flashLoanAsset != vaultDepositAsset) {
            // Swap flash loaned asset to vault deposit asset
            // Approve the full amount needed for the swap
            bytes4 swapSelector = bytes4(depositData.inputData.swapParams);
            require(swapSelector == swapCompactSelector, "Invalid swap selector");
            IERC20(flashLoanAsset).safeApprove(odosRouter, type(uint256).max);
            uint256 beforeBalance = IERC20(vaultDepositAsset).balanceOf(address(this));
            // Execute the swap
            (bool success, ) = odosRouter.call(depositData.inputData.swapParams);
            require(success, "Swap failed");
            IERC20(flashLoanAsset).safeApprove(odosRouter, 0);
            swapAmountoutput = IERC20(vaultDepositAsset).balanceOf(address(this)) - beforeBalance;
        } else if (
            flashLoanAsset == vaultDepositAsset &&
            depositData.inputData.depositAsset != vaultDepositAsset
        ) {
            bytes4 swapSelector = bytes4(depositData.inputData.swapParams);
            require(swapSelector == swapCompactSelector, "Invalid swap selector");
            IERC20(depositData.inputData.depositAsset).safeApprove(odosRouter, type(uint256).max);
            uint256 beforeBalance = IERC20(vaultDepositAsset).balanceOf(address(this));

            (bool success, ) = odosRouter.call(depositData.inputData.swapParams);
            IERC20(depositData.inputData.depositAsset).safeApprove(odosRouter, 0);
            require(success, "Swap failed");
            swapAmountoutput = IERC20(vaultDepositAsset).balanceOf(address(this)) - beforeBalance;
        }
        depositAmount += swapAmountoutput;

        IICHIVault ichiVault = IICHIVault(IBeefyVault(depositData.inputData.vicunaVault).want());
        bool isToken0 = ichiVault.token0() == vaultDepositAsset;
        // Deposit into ICHI vault
        IERC20(vaultDepositAsset).safeApprove(address(ichiVault), depositAmount);
        uint256 ichiBalance = IICHIVault(ichiVault).deposit(
            isToken0 ? depositAmount : 0,
            isToken0 ? 0 : depositAmount,
            address(this)
        );
        IERC20(vaultDepositAsset).safeApprove(address(ichiVault), 0);


        // Deposit ICHI LP tokens into Beefy vault
        IERC20(address(ichiVault)).safeApprove(depositData.inputData.vicunaVault, ichiBalance);
        IBeefyVault(depositData.inputData.vicunaVault).deposit(ichiBalance);
        IERC20(address(ichiVault)).safeApprove(depositData.inputData.vicunaVault, 0);


        // Supply Beefy vault tokens to Aave
        uint256 vaultBalance = IERC20(depositData.inputData.vicunaVault).balanceOf(address(this));
        IERC20(depositData.inputData.vicunaVault).safeApprove(address(pool), vaultBalance);
        pool.supply(depositData.inputData.vicunaVault, vaultBalance, depositData.sender, 0);
        IERC20(depositData.inputData.vicunaVault).safeApprove(address(pool), 0);

        // Borrow from Aave
        pool.borrow(depositData.inputData.borrowAsset, flashLoanAmount, 2, 0, depositData.sender);

        // Approve and repay flash loan
        IERC20(flashLoanAsset).approve(address(borrowPool), flashLoanAmount);
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

    receive() external payable {
        revert();
    }

}
