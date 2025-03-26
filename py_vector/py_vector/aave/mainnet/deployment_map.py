from typing import Any, Optional, Type

from brownie.network.contract import Contract, ProjectContract
from pydantic import BaseModel

from .contracts_containers import (DeployedContract, UnlockableAccount,
                                   get_global_ignore_connect,
                                   set_global_ignore_connect)


def generic_contract_serialiser(contract):
    contract_type = contract._name
    address = contract.address
    return {"contract": contract_type, "address": address}


def generic_disconnected_contract_serialiser(contract):
    contract_type = contract.contract
    data = {"contract": contract_type, "address": contract.address}
    ignore_connect = getattr(contract, "ignore_connect", None)
    if ignore_connect is not None:
        data["ignore_connect"] = True
    return data


def generic_account_serialiser(account):
    return account.address


class CustomSchema(BaseModel):
    class Config:
        arbitrary_types_allowed = True
        json_encoders = {
            Contract: generic_contract_serialiser,
            ProjectContract: generic_contract_serialiser,
            DeployedContract: generic_disconnected_contract_serialiser,
            UnlockableAccount: generic_account_serialiser,
        }

    def connect(self):
        self.dict(connect=True)

    def dict(self, connect=True, **kwargs):
        kwargs["exclude_none"] = True
        return_dict = super().dict(**kwargs)
        if not connect:
            return return_dict
        for key, item in return_dict.items():
            if isinstance(item, DeployedContract):
                return_dict[key] = item.get_connected()
        return return_dict

    def __getattribute__(self, __name: str) -> Any:
        target = super().__getattribute__(__name)
        if isinstance(target, DeployedContract):
            connected_contract = target.get_connected()
            setattr(self, __name, connected_contract)
            return connected_contract
        return target

    def get_all_upgradeable_contracts(self):
        contracts = []
        for field_name, field in self:
            if isinstance(field, CustomSchema):
                contracts += field.get_all_upgradeable_contracts()
            if isinstance(field, DeployedContract):
                if field.should_be_upgraded:
                    contracts.append(field)
        return contracts


class ERC20Contract(DeployedContract): ...


class AllTokens(CustomSchema):
    # USDC: ERC20Contract
    pass


class ProtocolDeploymentMap(CustomSchema):
    pass


class AccountsList(BaseModel):
    pass
    # deployer: UnlockableAccount
    # ptp_multisig: UnlockableAccount
    # born: UnlockableAccount
    # multisig_vector: UnlockableAccount
    # deployer_multisig: UnlockableAccount


class DeploymentMap(CustomSchema):
    tokens: AllTokens
    PROTOCOL: ProtocolDeploymentMap
    ACCOUNTS: AccountsList
