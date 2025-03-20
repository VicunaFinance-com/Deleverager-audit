pragma solidity ^0.8.10;


struct Price {
    // Price
    int64 price;
    // Confidence interval
    uint64 conf;
    // Price exponent
    int32 expo;
    // Unix timestamp describing when the price was published
    uint publishTime;
}

interface IPyth {
    function getPrice(bytes32 priceId) external view returns (Price memory);
    function getEmaPrice(bytes32 priceId) external view returns (Price memory);
    function getPriceUnsafe(bytes32 priceId) external view returns (Price memory);
    function getUpdateFee(bytes[] calldata priceUpdateData) external view returns (uint256);
    function updatePriceFeeds(bytes[] calldata priceUpdateData) external payable;
    function getPriceNoOlderThan(
        bytes32 id,
        uint age
    ) external view returns (Price memory price);
}