// SPDX-License-Identifier: BUSL-1.1
pragma solidity ^0.8.0;

contract MockOracle {
  int256 private _latestAnswer;
  uint256 constant public decimals = 8;

  event AnswerUpdated(int256 indexed current, uint256 indexed roundId, uint256 updatedAt);

  constructor(int256 initialAnswer) {
    _latestAnswer = initialAnswer;
    emit AnswerUpdated(initialAnswer, 0, block.timestamp);
  }

  function setAnswer(int256 value) external {
    _latestAnswer = value;
    emit AnswerUpdated(value, 0, block.timestamp);
  }
  function latestAnswer() external view returns (int256) {
    return _latestAnswer;
  }
}
