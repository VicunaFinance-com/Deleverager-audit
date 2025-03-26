import os
from enum import Enum
from pathlib import Path
from typing import Union

from brownie import project


def find_root(anchor: str = ".git", max_depth=10):
    current_dir = Path(os.getcwd())
    for _ in range(max_depth):
        if (current_dir / anchor).exists():
            return current_dir
        current_dir = current_dir.parent
    return Path(os.getcwd())


REPOSITORY_ROOT = find_root()


def load_project_item(project_path: Union[str, Path]) -> project.main.Project:
    current_dir = Path(os.getcwd())
    try:
        os.chdir(current_dir / project_path)
        requested_project = project.load(".", raise_if_loaded=False)
    except:
        os.chdir(current_dir)
        raise

    os.chdir(current_dir)
    return requested_project


class ProjectPath:
    proxies = REPOSITORY_ROOT / "common-contracts/proxies"


# TODOLATER : Add utils funcs here to laod projects even faster
