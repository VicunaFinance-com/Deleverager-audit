# vector package init file
import os
from enum import Enum

from dotenv import load_dotenv

from . import utils
from .common.network.gas_strategies import get_snowtrace_strategy
from .common.testing import debug_decorator
from .common.upgrades import deploy_upgradeable_contract


class ProjectName(Enum):
    AAVE = "aave"
    NONE = None


load_dotenv()
PROJECT_NAME = ProjectName[os.environ.get("PROJECT_NAME", "None").upper()]

from . import aave, common
from .aave import DeploymentMap, get_deployment

SNOWTRACE_TOKEN = os.getenv("SNOWTRACE_TOKEN", None)
