import json
import os

import requests
from brownie import Contract, config, web3
from brownie.project import compiler

from py_vector.common.misc import pad_hex
from py_vector.common.network import (IS_ARBITRUM_MAINNET, IS_AVAX_MAINNET,
                                      IS_MAINNET)

BASE_URL = "https://api.sonicscan.org/api"
network_name = "aave"
if IS_MAINNET:
    BASE_URL = "https://andromeda-explorer.metis.io/api"
    network_name = "metis"
if IS_ARBITRUM_MAINNET:
    BASE_URL = "https://api.arbiscan.io/api"
    network_name = "arbitrum"


DEFAULT_EVM_VERSION = config["compiler"].get("evm_version") or "istanbul"
VERSION = config["compiler"]["solc"].get("version") or "0.8.7"
CACHE_SLOTS_FILE = f"{os.path.dirname(__file__)}/../../{network_name}/mainnet/slots_cache.json"

if not os.path.isfile(CACHE_SLOTS_FILE):
    with open(CACHE_SLOTS_FILE, "w+") as fp:
        json.dump({}, fp)


class StorageMismatch(Exception):
    contract_name: str
    address: str

    def __init__(self, name, address):
        self.contract_name = name
        self.address = address

    def __repr__(self):
        return f"Storage has been corrupted for contract {self.contract_name} at address {self.address}"


def get_contract_from_explorer(contract_address, ignore_proxy=False):
    if not isinstance(contract_address, str):
        contract_address = contract_address.address
    data = requests.get(
        f"{BASE_URL}?module=contract&action=getsourcecode&address={contract_address}&apikey=KPKM4I9UFM2UKA9PKE5KNYGJPZ598TCB1C"
    )
    data = data.json()["result"][0]
    print(data.keys())
    if (data.get("Proxy") == "1" or data.get("IsProxy") == "true") and not ignore_proxy:
        contract_address = data.get("Implementation", "") + data.get("ImplementationAddress", "")
        if contract_address == "":
            raise Exception("No implementation address retrieved")
    print(contract_address)
    contract = Contract.from_explorer(contract_address)
    return contract


def get_input_json_from_local_contract(contract):
    try:
        input_dict = contract.get_verification_info()["standard_json_input"]
    except IndexError:
        print("Error when generating the input_json, deployment.LIBS.connect()")
    compiler = config["compiler"]
    settings = {
        "evmVersion": compiler["evm_version"] or DEFAULT_EVM_VERSION,
        "optimizer": compiler["solc"]["optimizer"],
        "outputSelection": {
            "*": {
                "*": ["storageLayout"],
                list(input_dict["sources"].keys())[0]: ["ast"],
            }
        },
    }
    input_dict["settings"] = settings
    return input_dict


def get_input_json_from_explorer_contract_sources(sources):
    sources = {key: {"content": value} for key, value in sources.items()}

    input_dict = {"language": "Solidity", "sources": sources}
    compiler = config["compiler"]
    settings = {
        "evmVersion": compiler["evm_version"] or DEFAULT_EVM_VERSION,
        "optimizer": compiler["solc"]["optimizer"],
        "outputSelection": {"*": {"*": ["storageLayout"], list(sources.keys())[0]: ["ast"]}},
    }
    input_dict["settings"] = settings
    return input_dict


def get_input_json_from_explorer_contract(contract):
    sources = contract._sources
    return get_input_json_from_explorer_contract_sources(sources)


def get_storage_from_explorer_contract(address, contract_name, **kwargs):
    output_json = Contract.storage_from_explorer(address, **kwargs)
    candidates = [
        key
        for key in output_json["contracts"]
        if key.split("/")[-1].upper() == f"{contract_name}.sol".upper()
    ]
    if not candidates:
        candidates = [
            key for key in output_json["contracts"] if contract_name in key.split("/")[-1]
        ]
    print(output_json["contracts"].keys())
    print(contract_name)
    best_key = candidates[0]
    return output_json["contracts"][best_key][contract_name]["storageLayout"]


def get_storage_layout_from_input_json(input_json, contract_name):
    output_json = compiler.solidity.compile_from_input_json(input_json)
    best_key = [
        key for key in output_json["contracts"] if key.split("/")[-1] == f"{contract_name}.sol"
    ][0]
    return output_json["contracts"][best_key][contract_name]["storageLayout"]


def infer_contract_name(contract):
    name = contract._build["contractName"]
    return name


def check_storage(
    contract,
    explorer_address,
    is_proxy=True,
    raise_on_failure=True,
    ignore_renames=True,
):
    compiler.set_solc_version(str(VERSION))
    contract_name = infer_contract_name(contract)
    local_storage = get_storage_layout_from_input_json(
        get_input_json_from_local_contract(contract), contract_name
    )
    try:
        current_storage = get_storage_layout_from_input_json(
            get_input_json_from_explorer_contract(get_contract_from_explorer(explorer_address)),
            contract_name,
        )
    except:
        current_storage = get_storage_from_explorer_contract(explorer_address, contract_name)
    local_storage = refine_storage(local_storage)
    current_storage = refine_storage(current_storage)

    max_local_storage_slot = list(local_storage.keys())[-1]
    if local_storage[max_local_storage_slot]["label"] == "__gap":
        local_storage.pop(max_local_storage_slot, None)

    max_current_storage_slot = list(current_storage.keys())[-1]
    if current_storage[max_current_storage_slot]["label"] == "__gap":
        current_storage.pop(max_current_storage_slot, None)

    if ignore_renames:
        remove_all_labels(current_storage)
        remove_all_labels(local_storage)

    is_storage_consistent = all(
        current_storage[key] == local_storage[key] for key in current_storage
    )
    if raise_on_failure and not is_storage_consistent:
        raise StorageMismatch(contract_name, explorer_address)
    return is_storage_consistent


def remove_all_labels(storage_json):
    for key in storage_json:
        if "label" in storage_json[key]:
            del storage_json[key]["label"]
    return storage_json


def refine_storage(storage_json):
    storage = storage_json["storage"]
    types = storage_json["types"]
    for idx, item in enumerate(storage):
        value_type = item.pop("type")
        associated_type = types[value_type]
        if "astId" in item:
            del item["astId"]
        if "members" in associated_type:
            for element in associated_type["members"]:
                del element["astId"]
        if "value" in associated_type:
            del associated_type["value"]
        if "base" in associated_type:
            del associated_type["base"]
        type_label = associated_type["label"]
        associated_type["type_label"] = type_label
        item = {**associated_type, **item}
        item["contract"] = item["contract"].split(":")[-1]
        storage[idx] = item
    return {row["slot"]: row for row in storage}


def infer_slot_for_variable(contract_address, variable_name, is_strict=True):
    storage_layout = get_storage_layout(contract_address)
    results = {
        row["label"]: row["slot"]
        for row in storage_layout["storage"]
        if variable_name in row["label"]
    }
    if variable_name in results:
        return {variable_name: results[variable_name]}
    if is_strict:
        return {}
    else:
        return results


def get_storage_layout(contract_address):
    contract_address = getattr(contract_address, "contract_address", contract_address)
    contract = get_contract_from_explorer(contract_address)
    contract_name = infer_contract_name(contract)
    storage_layout = get_storage_from_explorer_contract(contract_address, contract_name)
    return storage_layout


def write_value_to_slot(address, slot, value):
    slot = str(slot)
    address = getattr(address, "address", address)
    if isinstance(value, int):
        value = hex(value)
    value = str(value)
    value = pad_hex(value)
    web3.provider.make_request("anvil_setStorageAt", [address, slot, value])


def compute_mapping_slot(base_slot, *keys):
    if str(base_slot)[:2] != "0x":
        base_slot = int(base_slot)
    if isinstance(base_slot, int):
        base_slot = hex(base_slot)
    base_slot = str(base_slot)
    for key in keys:
        key = str(key)
        to_encode = pad_hex(pad_hex(key) + pad_hex(base_slot), 128)[2:]
        slot = web3.sha3(hexstr=to_encode).hex()
        base_slot = slot
    return slot


def infer_balances_slot(contract_address, specified_name=None):
    if specified_name:
        candidates = infer_slot_for_variable(contract_address, specified_name, is_strict=True)
    else:
        candidates = infer_slot_for_variable(contract_address, "balance", is_strict=False)
    if len(candidates) == 0:
        raise Exception("No slot found")
    if len(candidates) > 1:
        raise Exception(f"Slot candidates were found, but not uniques: {candidates}")
    return list(candidates.items())[0]


def write_balance(token, account, value, refresh_slot=False, slot_name=None):
    token = getattr(token, "address", token)
    slot = get_balance_slot(token, refresh=refresh_slot, slot_name=slot_name)
    slot = compute_mapping_slot(slot, account)
    write_value_to_slot(token, slot, value)


def get_balance_slot(address, refresh=False, slot_name=None):
    slot = read_slot_from_cache(address, "balances")
    if slot is None or refresh:
        write_slot_to_cache(
            address,
            "balances",
            infer_balances_slot(address, specified_name=slot_name)[1],
        )
    slot = read_slot_from_cache(address, "balances")
    if slot is None:
        raise SlotNotFound(address, "balances")
    return slot


class SlotNotFound(Exception):
    def __init__(self, address, slot_name):
        super.__init__(
            f"{address} cannot detect a {slot_name} (slot name can be actually a bit different"
        )


def write_slot_to_cache(address, slot_name, slot_id):
    cache = json.load(open(CACHE_SLOTS_FILE, "r+"))

    if address not in cache:
        cache[address] = {}

    cache[address][slot_name] = slot_id

    json.dump(cache, open(CACHE_SLOTS_FILE, "w"), indent=4, sort_keys=True)


def read_slot_from_cache(address, slot_name):
    cache = json.load(open(CACHE_SLOTS_FILE, "r+"))

    if address not in cache:
        return None
    return cache[address][slot_name]
