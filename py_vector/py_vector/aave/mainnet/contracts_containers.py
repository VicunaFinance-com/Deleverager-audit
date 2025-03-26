import os
from dataclasses import dataclass
from enum import Enum, auto
from typing import NamedTuple, Tuple, Union

from brownie import ZERO_ADDRESS, accounts, interface
from brownie.network.contract import ContractContainer, InterfaceContainer

connected_contracts = []
ALL_CONTRACTS = {}
UPGRADE_WATCHLIST = []

GLOBAL_SHOULD_IGNORE_CONNECT = None


class ContractsContainersMapping(Enum):
    # MainStaking = MainStaking
    pass


class InterfacesContainersMapping(Enum):
    IERC20 = interface.IERC20


class UnlockableAccount(str):
    address = None

    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, val):
        return cls(val)

    def __init__(self, val):
        self.address = val
        assert val[:2] == "0x"
        assert len(val) == 42

    def unlock(self):
        os.getenv("SNOWTRACE_TOKEN", None)
        return accounts.at(self.address, force=True)

    def parameters(self, **kwargs):
        return {"from": self.unlock(), **kwargs}

    def __repr__(self):
        return self.address


class ContractType(Enum):
    contract = auto()
    interface = auto()


def set_global_ignore_connect(state):
    global GLOBAL_SHOULD_IGNORE_CONNECT
    GLOBAL_SHOULD_IGNORE_CONNECT = state


def get_global_ignore_connect():
    return GLOBAL_SHOULD_IGNORE_CONNECT


def resolve_contract_type(contract_name):
    contract_type = None
    try:
        contract_container = ContractsContainersMapping[contract_name].value
        contract_type = ContractType.contract
    except KeyError as e:
        try:
            contract_container = InterfacesContainersMapping[contract_name].value
            contract_type = ContractType.interface
        except KeyError:
            return None, None
    return contract_container, contract_type


@dataclass
class DeployedContract:
    contract: Union[ContractContainer, InterfaceContainer, str]
    address: str
    ignore_connect: bool = False
    should_be_upgraded: bool = False

    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, values):
        if values.get("should_be_upgraded"):
            UPGRADE_WATCHLIST.append(values.get("address"))
        if values.get("address") == "":
            values["address"] = ZERO_ADDRESS
        return cls(**values)

    def get_connected(self):
        global ALL_CONTRACTS
        values = self.__dict__
        __ignore_connect = values.get("ignore_connect", False)
        if GLOBAL_SHOULD_IGNORE_CONNECT is not None:
            __ignore_connect = GLOBAL_SHOULD_IGNORE_CONNECT

        contract = values.get("contract")
        address = values["address"]
        if address == ZERO_ADDRESS or len(address) == 0:
            __ignore_connect = True
        if __ignore_connect:
            return self
        contract_container, contract_type = resolve_contract_type(contract)
        if contract_container is None:
            raise Exception(
                f"Incorrect contracts mapping in contracts_containers for {contract} at {address}"
            )
        if contract_type == ContractType.contract:
            ALL_CONTRACTS[address] = contract_container
            return contract_container.at(address)
        if contract_type == ContractType.interface:
            return contract_container(address)

    def __str__(self):
        return self.address

    def dict(self):
        return self.get_connected()

    def resolve(self):
        return resolve_contract_type(self.contract)
