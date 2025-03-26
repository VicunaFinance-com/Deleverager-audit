import os
from contextlib import contextmanager
from typing import Generator, Union

from brownie import interface
from brownie.network.contract import ContractContainer
from omegaconf import OmegaConf

from .deployment_map import (
    DeployedContract,
    DeploymentMap,
    ProjectContract,
    get_global_ignore_connect,
    set_global_ignore_connect,
)

deployment_data = OmegaConf.load(f"{os.path.dirname(__file__)}/deployment.yaml")

cached_deployment = None
last_created_deployment = None


def get_last_created_deployment() -> DeploymentMap:
    return last_created_deployment


def get_deployment(from_cache=True, overwrite=False) -> DeploymentMap:
    global cached_deployment
    global last_created_deployment
    if not from_cache:
        deployment = DeploymentMap.parse_obj(deployment_data)
        if overwrite:
            cached_deployment = deployment
        last_created_deployment = cached_deployment
        return deployment
    if cached_deployment is None:
        cached_deployment = DeploymentMap.parse_obj(deployment_data)
        last_created_deployment = cached_deployment
    return cached_deployment


@contextmanager
def no_connect_deployment() -> Generator[DeploymentMap, None, None]:
    initial_value = get_global_ignore_connect()
    set_global_ignore_connect(True)
    try:
        yield get_deployment(from_cache=False)
    finally:
        set_global_ignore_connect(initial_value)


def as_proxy(contract: Union[DeployedContract, str, ProjectContract, ContractContainer]):
    if isinstance(contract, str):
        address = contract
    else:
        address = contract.address
    return interface.ITransparentUpgradeableProxy(address)
