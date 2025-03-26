// SPDX-License-Identifier: BUSL-1.1
pragma solidity ^0.8.10;

import {AggregatorInterface} from "../dependencies/chainlink/AggregatorInterface.sol";
import {IERC20} from "../dependencies/openzeppelin/contracts/IERC20.sol";
import {IPyth, Price} from "../interfaces/IPyth.sol";
import {Ownable} from "../dependencies/openzeppelin/contracts/Ownable.sol";
import {IPeggedOracle} from "../interfaces/IPeggedOracle.sol";

interface ISwapXOracle {
    function getTokenAmounts(
        uint256 lpAmount
    ) external view returns (uint256[] memory amounts, address[] memory tokens);

    function sharesToLp(uint256 shareAmount) external view returns (uint256);
}

contract UiHelper is Ownable {
    uint8 private constant _STANDARD_DECIMALS = 8;

    enum MarketType {
        MAIN,
        SONIC,
        STABLE
    }
    enum TokenType {
        CLASSIC,
        ICHI,
        BEATS
    }

    struct TokenId {
        address token;
        MarketType marketType;
    }

    struct TokenAmounts {
        address[] tokens;
        uint256[] amounts;
    }
    struct MarketInfos {
        address oracle;
        TokenType tokenType;
    }
    // Mapping of token address to its oracle configuration
    mapping(address => mapping(MarketType => MarketInfos)) public tokens;

    function addToken(TokenId calldata tokenId, MarketInfos calldata marketInfos) public onlyOwner {
        tokens[tokenId.token][tokenId.marketType] = marketInfos;
    }

    function getTokensForInput(
        TokenId[] calldata tokenIds,
        uint256[] calldata amounts
    ) external view returns (TokenAmounts[] memory result) {
        uint256 maxIdx = tokenIds.length;
        result = new TokenAmounts[](maxIdx);
        for (uint256 idx; idx < maxIdx; idx++) {
            TokenId memory tokenId = tokenIds[idx];
            MarketInfos memory infos = tokens[tokenId.token][tokenId.marketType];
            TokenAmounts memory results;
            if (infos.tokenType == TokenType.ICHI) {
                (results.amounts, results.tokens) = ISwapXOracle(infos.oracle).getTokenAmounts(
                    ISwapXOracle(infos.oracle).sharesToLp(amounts[idx])
                );
            }
            result[idx] = results;
        }
    }
}
