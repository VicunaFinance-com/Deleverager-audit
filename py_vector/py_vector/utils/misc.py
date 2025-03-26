import json
from enum import Enum
from pathlib import Path

import requests
from brownie import Wei, web3


def get_bytecode(address: str):
    if isinstance(address, str):
        address = address
    else:
        address = address.address
    address = web3.toChecksumAddress(address.lower())
    return web3.eth.get_code(address).hex()[2:]


def find_containers_from_address(address):
    from py_vector import PROJECT_NAME, ProjectName

    if PROJECT_NAME == ProjectName.VECTOR:
        from py_vector.vector.mainnet.contracts_containers import ALL_CONTRACTS
    if PROJECT_NAME == ProjectName.METIS:
        from py_vector.metis.mainnet.contracts_containers import ALL_CONTRACTS
    if PROJECT_NAME == ProjectName.ARBITRUM:
        from py_vector.arbitrum.mainnet.contracts_containers import ALL_CONTRACTS
    return ALL_CONTRACTS.get(address)


def pad_hex(hex_str, pad_size=64):
    return "0x" + hex_str.replace("0x", "").rjust(pad_size, "0")


def write_to_files(base_path, files_to_write):
    base_path = Path(base_path)
    for key, file_contents in files_to_write.items():
        (base_path / Path(key.rsplit("/", 1)[0])).mkdir(parents=True, exist_ok=True)
        sub_path = base_path / Path(key)
        with open(sub_path, "w") as f:
            f.write(file_contents)


def get_sources_of(address, url_getter, only_implementation=True):
    res = requests.get(url_getter(address))
    data = json.loads(res.text)["result"][0]
    if data["Proxy"] != "0" and only_implementation:
        return get_sources_of(data["Implementation"])

    sources_str = data["SourceCode"]
    sources_str = sources_str.replace("\r\n", "")[1:-1]
    return {key: val["content"] for key, val in json.loads(sources_str)["sources"].items()}


def main_avax_sources_getter(address):
    url = f"https://api.snowtrace.io/api?module=contract&action=getsourcecode&address={address}&apikey=YourApiKeyToken"
    return url


def fuji_sources_getter(address):
    url = f"https://api-testnet.snowtrace.io/api?module=contract&action=getsourcecode&address={address}&apikey=YourApiKeyToken"
    return url


def metis_sources_getter(address):
    url = f"https://andromeda-explorer.metis.io/api?module=contract&action=getsourcecode&address={address}"
    return url


def arbitrum_sources_getter(address):
    url = f"https://api.snowtrace.io/api?module=contract&action=getsourcecode&address={address}&apikey=YourApiKeyToken"
    return url


class ApiSourceGetter(Enum):
    FUJI: fuji_sources_getter
    AVAX: main_avax_sources_getter
    METIS: metis_sources_getter
    ARBITRUM: arbitrum_sources_getter
