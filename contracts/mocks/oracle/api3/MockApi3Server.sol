// SPDX-License-Identifier: BUSL-1.1
pragma solidity ^0.8.0;

contract MockApi3Server {
    int256 private _latestAnswer;
    uint256 public constant decimals = 18;
    address public api3ServerV1;
    struct PriceData {
        int224 value;
        uint32 timestamp;
    }
    mapping(bytes32 => PriceData) public dataFeeds;
    event UpdatedBeaconSetWithBeacons(bytes32 indexed beaconSetId, int224 value, uint32 timestamp);

    function dapiNameToDataFeedId(bytes32 arg) public pure returns (bytes32) {
        return arg;
    }

    function setPrice(bytes32 feedId, int224 price) external {
        dataFeeds[feedId] = PriceData(price, uint32(block.timestamp));
        emit UpdatedBeaconSetWithBeacons(feedId, price, uint32(block.timestamp));
    }
}
