import json

from brownie import MainStaking, MainStakingJoe

# DEPRECATED : gist of it included in brownie.network.contract file
# The publish_source should be abloe to verify anything now


def generate_main_staking_json(fp=None):
    data = MainStaking.get_verification_info()["standard_json_input"]
    result = flatten_libraries_for_file(data)
    if fp is None:
        return result
    if isinstance(fp, str):
        json.dump(result, open(fp, "w"))
        return result
    json.dump(result, fp)
    return result


def generate_main_staking_joe_json(fp=None):
    data = MainStakingJoe.get_verification_info()["standard_json_input"]
    result = flatten_libraries_for_file(data)
    if fp is None:
        return result
    if isinstance(fp, str):
        json.dump(result, open(fp, "w"))
        return result
    json.dump(result, fp)
    return result


def flatten_libraries_for_file(data):
    sources = data["sources"]
    libraries = data["settings"]["libraries"]
    files_requiring_libraries = list(libraries.keys())
    file_to_flatten = files_requiring_libraries[0]
    libraries_files = [name.replace(".sol", "") + ".sol" for name in libraries[file_to_flatten]]
    processed_lines = []
    ms_source = sources[file_to_flatten]["content"].split("\n")
    for _, line in enumerate(ms_source):
        if "import" in line and any(file_name in line for file_name in libraries_files):
            file_name = [name for name in libraries_files if name in line][0]
            line = get_stripped_library(file_name, sources)
        processed_lines.append(line)
    new_source = "\n".join(processed_lines)
    data["sources"][file_to_flatten] = {"content": new_source}
    for library_name in libraries_files:
        data["sources"].pop(library_name)
    return data


def get_stripped_library(name, sources):
    library_source = sources[name]["content"].split("\n")
    lines = []
    for line in library_source:
        if "pragma" in line:
            continue
        if "license" in line.lower():
            continue
        lines.append(line)
    return "\n".join(lines)
