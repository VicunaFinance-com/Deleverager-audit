from typing import List, Optional

from brownie import (
    Contract,
    ProxyAdmin,
    TransparentUpgradeableProxy,
    Wei,
    chain,
    interface,
    web3,
)
from brownie.exceptions import VirtualMachineError
from py_vector.common.network import IS_AVAX_MAINNET
from py_vector.common.upgrades import (
    get_admin_address_for_proxy,
    get_implementation_address_for_proxy,
    should_upgrade,
)
from py_vector.vector.mainnet import ALL_CONTRACTS, get_deployment
from py_vector.vector.mainnet.contracts_containers import resolve_contract_type
from py_vector.vector.mainnet.deployed_contracts import (
    DeployedContract,
    no_connect_deployment,
)

DEPLOYMENT = get_deployment()


def get_outdated_contracts(watchlist: Optional[List[str]] = None):
    if watchlist is None:
        with no_connect_deployment() as deployment:
            watchlist = deployment.get_all_upgradeable_contracts()
    should_be_upgraded = []
    for contract in watchlist:
        contract_container = contract
        if isinstance(contract, DeployedContract):
            contract_container, _ = contract.resolve()
            contract = contract.get_connected()
        else:
            contract_container, _ = resolve_contract_type(contract._build["contractName"])
        implementation_address = get_implementation_address_for_proxy(contract.address)
        if (
            should_upgrade(contract_container, implementation_address)
            and implementation_address != "0x"
        ):
            should_be_upgraded.append(contract)

    return should_be_upgraded


def mass_upgrade_to_current_state(addresses: Optional[List[str]] = None):
    if addresses is None:
        addresses = get_outdated_contracts()

    deployment = get_deployment()
    deployer = deployment.ACCOUNTS.deployer
    deployment.LIBS.dict(connect=True)
    global_proxy_timer = 0

    addresses = [getattr(address, "address", address) for address in addresses]

    for address in addresses:
        contract_to_upgrade_container = ALL_CONTRACTS[address]
        new_implementation = contract_to_upgrade_container.deploy(deployer.parameters())
        transparent_proxy = interface.ITransparentUpgradeableProxy(address)
        proxy_admin = interface.ITimelockedProxyAdmin(
            get_admin_address_for_proxy(transparent_proxy)
        )

        proxy_timer = 0
        try:
            proxy_timer = proxy_admin.timelockLength()
        except VirtualMachineError:
            proxy_timer = transparent_proxy.timelockLength()
        except Exception as e:
            print(e)
            raise e
        if not IS_AVAX_MAINNET:
            chain.mine()
            proxy_admin.submitUpgrade(
                transparent_proxy, new_implementation, {"from": proxy_admin.owner()}
            )
        proxy_timer = max(proxy_timer, transparent_proxy.timelockLength())
        global_proxy_timer = max(global_proxy_timer, proxy_timer) + 1
    if IS_AVAX_MAINNET:
        return

    chain.sleep(global_proxy_timer)
    chain.mine()
    for address in addresses:
        transparent_proxy = interface.ITransparentUpgradeableProxy(address)
        proxy_admin = interface.ITimelockedProxyAdmin(
            get_admin_address_for_proxy(transparent_proxy)
        )
        proxy_admin.upgrade(transparent_proxy, {"from": proxy_admin.owner()})
    # TODOLATER: take care of libraries, add condition for upgrade
