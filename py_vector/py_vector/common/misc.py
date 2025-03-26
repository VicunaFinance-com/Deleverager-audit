import json

import requests
from brownie import Wei, chain, history, interface, web3
from py_vector.utils.misc import *


def insert_libs_in_bytecode(bytecode):
    from py_vector import get_deployment

    deployment = get_deployment(from_cache=False)
    if hasattr(deployment, "LIBS"):
        libs_dict = deployment.LIBS.dict(connect=False)
        for lib in libs_dict.values():
            lib_address = lib.address
            lib_name = f"__{lib.contract}".ljust(40, "_")
            bytecode = bytecode.replace(lib_name, lib_address[2:])
    return bytecode


class Infix:
    """
    Class to create infix operators in order to simplify writing
    The operator has the same priority level as the operator that is used (here mul)
    Let op be an operator assosiated with the function foo
    a *op* b == foo(a,b)
    """

    def __init__(self, function):
        self.function = function

    def __rmul__(self, other):
        return Infix(lambda x, self=self, other=other: self.function(other, x))

    def __mul__(self, other):
        return self.function(other)

    def __rlshift__(self, other):
        return Infix(lambda x, self=self, other=other: self.function(other, x))

    def __rshift__(self, other):
        return self.function(other)

    def __call__(self, value1, value2):
        return self.function(value1, value2)


of = Infix(lambda units, token: Wei(units) * 10 ** interface.IERC20Metadata(token).decimals())
in_units = Infix(
    lambda units, token: Wei(units) // (10 ** interface.IERC20Metadata(token).decimals())
)


def relative_delta(a, b):
    return (a - b) / b
