// SPDX-License-Identifier: BUSL-1.1
pragma solidity ^0.8.0;

contract MockChainlinkServer {
    int256 private _latestAnswer;
    uint256 public constant decimals = 18;
    uint256 public round = 0;
    event AnswerUpdated(int256 indexed current, uint256 indexed roundId, uint256 updatedAt);

    function dapiNameToDataFeedId(bytes32 arg) public pure returns (bytes32) {
        return arg;
    }

    function latestAnswer() external view returns (int256) {
        return _latestAnswer;
    }

    function setPrice(int256 price) external {
        _latestAnswer = price;
        round += 1;
        emit AnswerUpdated(price, round, block.timestamp);
    }
}
