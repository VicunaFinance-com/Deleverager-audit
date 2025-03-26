import os
from enum import Enum
from logging import warn
from typing import Generator, Union

import eth_utils
from brownie import Contract, Wei, chain, interface, web3
from brownie.network.contract import ContractContainer

from py_vector.common.misc import (get_bytecode, insert_libs_in_bytecode,
                                   pad_hex)
from py_vector.common.projects import ProjectPath, load_project_item

from . import storage


class TransparentProxyVersion(int, Enum):
    V1 = 1
    V2 = 2


TRANSPARENT_PROXY_VERSION = TransparentProxyVersion[os.environ.get("PROXY_VERSION", "V2")]


def get_transparent_proxy_version():
    global TRANSPARENT_PROXY_VERSION
    return TRANSPARENT_PROXY_VERSION


def set_transparent_proxy_version(version: TransparentProxyVersion):
    global TRANSPARENT_PROXY_VERSION
    TRANSPARENT_PROXY_VERSION = version


def get_slot_for_string(str):
    return hex(int(web3.keccak(text=str).hex(), 16) - 1)


int_from_hex = lambda x: int(x, 16)
ADMIN_SLOT = 0xB53127684A568B3173AE13B9F8A6016E243E63B6E8EE1178D6A717850B5D6103
IMPLEMENTATION_SLOT = 0x360894A13BA1A3210667C828492DB98DCA3E2076CC3735A920A3CA505D382BBC
NEXT_IMPLEMENTATION_SLOT = int_from_hex(get_slot_for_string("eip1967.proxy.nextImplementation"))


def get_admin_address_for_proxy(proxy: Union[str, ContractContainer]):
    if isinstance(proxy, str):
        address = proxy
    else:
        address = proxy.address
    address = web3.toChecksumAddress(address.lower())
    return (
        web3.eth.get_storage_at(address, ADMIN_SLOT)
        .hex()
        .ljust(42, "0")
        .replace("0x" + 24 * "0", "0x")
    )


def get_next_implementation_address_for_proxy(proxy: Union[str, ContractContainer]):
    if isinstance(proxy, str):
        address = proxy
    else:
        address = proxy.address
    address = web3.toChecksumAddress(address.lower())
    return (
        web3.eth.get_storage_at(address, NEXT_IMPLEMENTATION_SLOT)
        .hex()
        .ljust(42, "0")
        .replace("0x" + 24 * "0", "0x")
    )


def get_implementation_address_for_proxy(proxy: Union[str, ContractContainer]):
    if isinstance(proxy, str):
        address = proxy
    else:
        address = proxy.address
    address = web3.toChecksumAddress(address.lower())
    return (
        web3.eth.get_storage_at(address, IMPLEMENTATION_SLOT)
        .hex()
        .ljust(42, "0")
        .replace("0x" + 24 * "0", "0x")
    )


def should_upgrade(container, current_address):
    print(current_address)
    current_bytecode = get_bytecode(current_address)
    if not current_bytecode:
        return False
    new_bytecode = container.bytecode
    new_bytecode = insert_libs_in_bytecode(new_bytecode)

    return current_bytecode.upper() not in new_bytecode.upper()


def encode_function_data(initializer=None, *args):
    """Encodes the function call so we can work with an initializer.
    Args:
        initializer ([brownie.network.contract.ContractTx], optional):
        The initializer function we want to call. Example: `box.store`.
        Defaults to None.
        args (Any, optional):
        The arguments to pass to the initializer function
    Returns:
        [bytes]: Return the encoded bytes.
    """
    if not initializer:
        return eth_utils.to_bytes(hexstr="0x")
    else:
        return initializer.encode_input(*args)


def upgrade(
    account,
    proxy,
    new_implementation_address,
    proxy_admin_contract=None,
    initializer=None,
    *args,
):
    transaction = None
    if proxy_admin_contract:
        if initializer:
            encoded_function_call = encode_function_data(initializer, *args)
            transaction = proxy_admin_contract.upgradeAndCall(
                proxy.address,
                new_implementation_address,
                encoded_function_call,
                {"from": account},
            )
        else:
            transaction = proxy_admin_contract.upgrade(
                proxy.address, new_implementation_address, {"from": account}
            )
    else:
        if initializer:
            encoded_function_call = encode_function_data(initializer, *args)
            transaction = proxy.upgradeToAndCall(
                new_implementation_address, encoded_function_call, {"from": account}
            )
        else:
            transaction = proxy.upgradeTo(new_implementation_address, {"from": account})
    return transaction


def upgrade_in_tests_alt(
    account,
    proxy,
    new_implementation_address,
    proxy_admin_contract=None,
    initializer=None,
    *args,
):
    transaction = None
    proxy = Contract.from_abi(
        "TransparentUpgradeableProxy", proxy.address, TransparentUpgradeableProxy.abi
    )
    if proxy_admin_contract:
        if initializer:
            raise Exception("Not implemented")
        else:
            transaction = proxy_admin_contract.upgrade(
                proxy.address, new_implementation_address, {"from": account}
            )
    else:
        proxy.submitUpgrade(new_implementation_address, {"from": account})
        chain.sleep(proxy.timelockLength() + 1)
        if initializer:
            encoded_function_call = encode_function_data(initializer, *args)
            transaction = proxy.upgradeToAndCall(encoded_function_call, {"from": account})
        else:
            transaction = proxy.upgradeTo({"from": account})
    return transaction


def upgrade_in_tests(
    account,
    proxy,
    new_implementation_address,
    proxy_admin_contract=None,
    initializer=None,
    *args,
):
    transaction = None
    proxy = Contract.from_abi(
        "TransparentUpgradeableProxy", proxy.address, TransparentUpgradeableProxy.abi
    )
    if proxy_admin_contract:
        proxy_admin_contract.submitUpgrade(proxy, new_implementation_address, {"from": account})
        chain.sleep(proxy.timelockLength() + 1)
        if initializer:
            encoded_function_call = encode_function_data(initializer, *args)
            transaction = proxy_admin_contract.upgradeAndCall(
                proxy.address,
                encoded_function_call,
                {"from": account},
            )
        else:
            transaction = proxy_admin_contract.upgrade(proxy.address, {"from": account})
    else:
        proxy.submitUpgrade(new_implementation_address, {"from": account})
        chain.sleep(proxy.timelockLength() + 1)
        if initializer:
            encoded_function_call = encode_function_data(initializer, *args)
            transaction = proxy.upgradeToAndCall(encoded_function_call, {"from": account})
        else:
            transaction = proxy.upgradeTo({"from": account})
    return transaction


def deploy_upgradeable_contract(
    user_params, implementation_container, arg_name, proxy_admin=None, *args
):
    from brownie import ProxyAdmin

    proxy_version = get_transparent_proxy_version()
    transparent_proxy_container = _get_transparent_proxy_container(proxy_version)
    container_name = implementation_container._name

    implementation = implementation_container.deploy(user_params)

    implementation_encoded_initializer_function = encode_function_data(
        getattr(implementation, arg_name), *args
    )
    file_name = f"{container_name}__{implementation.address}.txt"
    # with open(file_name, 'w') as f:
    #     f.write(implementation_encoded_initializer_function)

    if not proxy_admin:
        proxy_admin = ProxyAdmin.deploy(user_params)
    contract = transparent_proxy_container.deploy(
        implementation.address,
        proxy_admin.address,
        implementation_encoded_initializer_function,
        user_params,
    )
    transparent_proxy_container.remove(contract)
    contract = implementation_container.at(contract)
    return contract, proxy_admin


def _get_transparent_proxy_container(proxy_version):
    if proxy_version == TransparentProxyVersion.V1:
        try:
            from brownie import TransparentUpgradeableProxy

            return TransparentUpgradeableProxy
        except ImportError:
            pass
        try:
            proxies = load_project_item(ProjectPath.proxies)
            if "TransparentUpgradeableProxy" in proxies:
                return proxies.TransparentUpgradeableProxy
        except:
            pass
        try:
            from brownie import \
                TransparentUpgradeableProxyV2 as TransparentUpgradeableProxy

            warn("V1 NOR FOUND, V2 LOADED")
        except ImportError:
            raise
    elif proxy_version == TransparentProxyVersion.V2:
        try:
            from brownie import \
                TransparentUpgradeableProxyV2 as TransparentUpgradeableProxy

            return TransparentUpgradeableProxy
        except ImportError:
            pass
        try:
            proxies = load_project_item(ProjectPath.proxies)
            if "TransparentUpgradeableProxyV2" in proxies:
                return proxies.TransparentUpgradeableProxyV2
        except:
            raise
    else:
        raise Exception(f"Invalid proxy version, {proxy_version}")
    return TransparentUpgradeableProxy


def deploy_upgradeable_contract_and_verify(
    user_params, implementation_container, arg_name, proxy_admin=None, *args
):
    from brownie import ProxyAdmin

    proxy_version = get_transparent_proxy_version()
    transparent_proxy_container = _get_transparent_proxy_container(proxy_version)

    container_name = implementation_container._name

    implementation = implementation_container.deploy(user_params, publish_source=True)
    implementation_encoded_initializer_function = encode_function_data(
        getattr(implementation, arg_name), *args
    )
    file_name = f"{container_name}__{implementation.address}.txt"
    # with open(file_name, 'w') as f:
    #     f.write(implementation_encoded_initializer_function)

    if not proxy_admin:
        proxy_admin = ProxyAdmin.deploy(user_params, publish_source=True)
    contract = transparent_proxy_container.deploy(
        implementation.address,
        proxy_admin.address,
        implementation_encoded_initializer_function,
        user_params,
        publish_source=True,
    )
    contract = Contract.from_abi(container_name, contract.address, implementation_container.abi)
    return contract, proxy_admin


def compute_mapping_slot(base_slot, *keys):
    base_slot = str(base_slot)
    for key in keys:
        key = str(key)
        to_encode = pad_hex(pad_hex(key) + pad_hex(base_slot), 128)[2:]
        slot = web3.sha3(hexstr=to_encode).hex()
        base_slot = slot
    return slot


def write_value_to_slot(address, slot, value):
    slot = str(slot)
    address = getattr(address, "address", address)
    if isinstance(value, (int, Wei)):
        value = hex(value)
    value = str(value)
    value = pad_hex(value)
    web3.provider.make_request("anvil_setStorageAt", [address, slot, value])
