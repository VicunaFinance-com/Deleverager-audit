// SPDX-License-Identifier: BUSL-1.1
pragma solidity ^0.8.0;

import {MockApi3Server} from "./MockApi3Server.sol";

contract MockApi3Proxy {
    int256 private _latestAnswer;
    uint256 public constant decimals = 18;
    address public api3ServerV1;
    bytes32 public dapiName;

    constructor(address server, bytes32 _dapiName) {
        api3ServerV1 = server;
        dapiName = _dapiName;
    }

    function latestAnswer() external view returns (int224, uint32) {
        return MockApi3Server(api3ServerV1).dataFeeds(dapiName);
    }

    function latestTimestamp() external view returns (uint256) {
        return block.timestamp;
    }
}
