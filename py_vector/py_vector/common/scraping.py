import json
import time

import requests
from py_vector import SNOWTRACE_TOKEN


class ScrapingConfig:
    api_key: str
    api_base_url: str

    def __init__(self, api_key, api_base_url):
        self.api_key = api_key
        self.api_base_url = api_base_url

    def url_getter(
        self,
        address,
        topic0=None,
        topic1=None,
        topic2=None,
        offset=100,
        startblock=1,
        endblock=99999999,
        sort="asc",
    ):
        url = (
            f"{self.api_base_url}?module=logs&action=getLogs&fromBlock={startblock}&endblock={endblock}"
            f"&offset={offset}&address={address}&apikey={self.api_key}&sort={sort}"
        )
        if topic0 is not None:
            url += f"&topic0={topic0}"
        if topic1 is not None:
            url += f"&topic1={topic1}"
        if topic2 is not None:
            url += f"&topic2={topic2}"

        return requests.get(url).json()


def get_paginated_event_request(
    address,
    topic0=None,
    topic1=None,
    topic2=None,
    offset=100,
    startblock=1,
    endblock=99999999,
    sort="asc",
    api_key=None,
):
    api_key = SNOWTRACE_TOKEN or "NN8PS81Y1D596ZRNK6M4SVD6VBCY893YD2"
    base_api = "https://api.routescan.io/v2/network/mainnet/evm/43114/etherscan/api"
    url = (
        f"{base_api}?module=logs&action=getLogs&address={address}&fromBlock={startblock}&toBlock={endblock}"
        f"&offset={offset}&sort={sort}&topic0_1_opr=and"
    )
    if topic0 is not None:
        url += f"&topic0={topic0}"
    if topic1 is not None:
        url += f"&topic1={topic1}"
    if topic2 is not None:
        url += f"&topic2={topic2}"

    return requests.get(url).json()


def get_all_events_for_account(
    address,
    topic0,
    topic1=None,
    topic2=None,
    offset=3000,
    startblock=1,
    endblock=99999999,
    sleep_time=0.25,
):
    all_tx = []
    last_block_fully_covered = 1
    while True:
        tx_page = get_paginated_event_request(
            address,
            topic0,
            topic1=topic1,
            topic2=topic2,
            offset=offset,
            startblock=startblock,
            endblock=endblock,
        )
        if tx_page["status"] == "0":
            break
        rows = tx_page["result"]
        print(len(rows), last_block_fully_covered, len(all_tx))
        all_tx += rows
        if len(rows) < 5:
            break
        blocks_on_last_page = list({int(row["blockNumber"], 16) for row in rows})
        if len(blocks_on_last_page) > 1:
            last_block_fully_covered = sorted(blocks_on_last_page)[-2]
            startblock = last_block_fully_covered + 1
            all_tx = [tx for tx in all_tx if int(tx["blockNumber"], 16) < startblock]
        time.sleep(sleep_time)
    return all_tx


def get_url_for_tx(address, page, page_size=30, startblock=1, endblock=99999999, sort="asc"):
    return f"https://api.snowtrace.io/api?module=account&action=txlist&address={address}&startblock={startblock}&endblock={endblock}&page={page}&offset={page_size}&sort={sort}&apikey=NN8PS81Y1D596ZRNK6M4SVD6VBCY893YD2"


def get_page_tx_for_account(
    address, page, page_size=30, startblock=1, endblock=99999999, sort="asc"
):
    return requests.get(
        get_url_for_tx(address, page, page_size, startblock, endblock, sort)
    ).json()


def get_all_tx_for_account(address, offset=3000, start_block=1, sleep_time=0.25):
    all_tx = []
    MAX_TX_IN_QUERY = 10000
    current_page = 1
    max_page = MAX_TX_IN_QUERY // offset
    last_block_fully_covered = 0
    while True:
        tx_page = get_page_tx_for_account(address, current_page, offset, startblock=start_block)
        if tx_page["status"] == "0":
            break
        rows = tx_page["result"]
        all_tx += rows

        blocks_on_last_page = list({int(row["blockNumber"]) for row in rows})
        if len(blocks_on_last_page) > 1:
            last_block_fully_covered = sorted(blocks_on_last_page)[-2]
        if current_page == max_page:
            current_page = 0
            start_block = last_block_fully_covered + 1
            all_tx = [tx for tx in all_tx if int(tx["blockNumber"]) < start_block]
        current_page += 1
        time.sleep(sleep_time)
    return all_tx


def get_sources_of(address, url_getter, only_implementation=True):
    res = requests.get(url_getter(address))
    data = json.loads(res.text)["result"][0]
    if data["Proxy"] != "0" and only_implementation:
        return get_sources_of(data["Implementation"])

    sources_str = data["SourceCode"]
    sources_str = sources_str.replace("\r\n", "")[1:-1]
    return {key: val["content"] for key, val in json.loads(sources_str)["sources"].items()}


def avax_sources_getter(address):
    url = f"https://api.snowtrace.io/api?module=contract&action=getsourcecode&address={address}&apikey=YourApiKeyToken"
    return url


def fuji_sources_getter(address):
    url = f"https://api-testnet.snowtrace.io/api?module=contract&action=getsourcecode&address={address}&apikey=YourApiKeyToken"
    return url
