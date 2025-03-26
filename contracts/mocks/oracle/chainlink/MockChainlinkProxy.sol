// SPDX-License-Identifier: BUSL-1.1
pragma solidity ^0.8.0;

import {MockChainlinkServer} from "./MockChainlinkServer.sol";

contract MockChainlinkProxy {
    int256 private _latestAnswer;
    uint256 public constant decimals = 18;
    address public api3ServerV1;

    address public aggregator;

    constructor(address _aggregator) {
        aggregator = _aggregator;
    }

    function latestAnswer() external view returns (int256) {
        return MockChainlinkServer(aggregator).latestAnswer();
    }
}
