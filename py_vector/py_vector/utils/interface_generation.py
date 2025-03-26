import json
import sys
from pathlib import Path

INTERFACES_PATH = Path("./interfaces")
BROWNIE_BUILD_PATH = Path("./build/contracts/")


def abi_input_to_func_defintion(abi_row):
    return_string = ""
    func_inputs = process_parameters_from_row(abi_row["inputs"], True)
    func_outputs = process_parameters_from_row(abi_row["outputs"], False)
    mutability = get_mutability_from_abi_row(abi_row)
    return_string = f'function {abi_row["name"]}({", ".join(func_inputs)}) {mutability}'
    if func_outputs:
        return_string += f' returns ({", ".join(func_outputs)})'
    return return_string + ";"


def get_mutability_from_abi_row(abi_row):
    mutability = abi_row.get("stateMutability", "nonpayble")

    if mutability == "payable":
        return "external payable"

    if mutability in ["view", "pure"]:
        return "external view"

    return "external"


def process_parameters_from_row(parameters, is_input, is_struct=False):
    processed_parameters = []
    for parameter_info in parameters:
        name = parameter_info["name"]
        arg_type = parameter_info["internalType"]
        was_struct = False
        if arg_type[:6] == "struct":
            arg_type = arg_type.split(".")[-1]
            was_struct = True

        if arg_type[:4] == "enum":
            arg_type = parameter_info["type"]

        if arg_type[:8] == "contract":
            arg_type = "address"

        if (
            was_struct or (arg_type[-2:] == "[]" or arg_type in ["string", "bytes"])
        ) and not is_struct:
            arg_type += " calldata" if is_input else " memory"
        if parameter_info.get("indexed", False):
            arg_type += " indexed"
        processed_parameters.append(arg_type + (f" {name}" if name else name))
        if "FarmInfoBMCJ" in arg_type:
            print(processed_parameters[-1], parameter_info)

    return processed_parameters


def process_structs_in_row(abi_row):
    all_params = abi_row["inputs"] + abi_row["outputs"]
    all_params_with_struct = [param for param in all_params if "components" in param]
    result = {}
    for param in all_params_with_struct:
        name = param["internalType"].split(".")[-1].replace("[]", "")
        result[name] = process_struct(param, name)
    return result


def process_event(abi_row):
    parameters = abi_row["inputs"]
    return_str = f'event {abi_row["name"]}('
    return_str += ",".join(process_parameters_from_row(parameters, True))
    return f"{return_str});"


def process_struct(struct_data, struct_name):
    return_str = f"struct {struct_name} " + "{\n"
    body = "\n".join(
        f"\t{process_parameters_from_row([param], False, True)[0]};"
        for param in struct_data["components"]
    )
    return return_str + body + "\n}"


def process_all_structs(abi):
    result = [process_structs_in_row(row) for row in abi]
    return [r for r in result if len(r)]


def process_all_events(abi):
    result = [process_event(row) for row in abi]
    return [r for r in result if len(r)]


def generate_interface_document_from_abi(contract_name, abi_data):
    if contract_name[0] == "I" and contract_name[1].isupper():
        return
    compiler_version = "0.8.7"
    functions = [row for row in abi_data if row["type"] == "function"]
    events = [row for row in abi_data if row["type"] == "event"]
    func_definition_body = get_function_definitions_body(functions)
    events_definition_body = get_events_definitions_body(events)
    struct_definition_body = get_structs_definitions_body(functions)
    interface_source = generate_template_document(
        contract_name,
        func_definition_body,
        struct_definition_body,
        events_definition_body,
        compiler_version,
    )
    with open(f"{INTERFACES_PATH}/I{contract_name}.sol", "w") as f:
        f.write(interface_source)
    return interface_source


def generate_interface_document_from_json(brownie_json):
    contract_name = brownie_json["contractName"]
    if contract_name[0] == "I" and contract_name[1].isupper():
        return
    abi_data = brownie_json["abi"]
    return generate_interface_document_from_abi(contract_name, abi_data)


def generate_template_document(
    contract_name,
    func_definition_body,
    structs_definition_body,
    events_definition_body,
    compiler_version,
):
    contract = f"// SPDX-License-Identifier: MIT\npragma solidity {compiler_version};\n\n"
    contract += f"interface I{contract_name}" + " {\n"
    lines = []
    if len(structs_definition_body):
        lines += (structs_definition_body + "\n\n").split("\n")
    if len(events_definition_body):
        lines += (events_definition_body + "\n\n").split("\n")
    lines += func_definition_body.split("\n")
    for idx, l in enumerate(lines):
        if l != "":
            lines[idx] = "\t" + l
    contract += "\n".join(lines)
    contract += "\n}"
    return contract


def get_structs_definitions_body(functions):
    structs = {}
    for result in process_all_structs(functions):
        structs.update(result)
    return "\n\n".join(structs.values())


def get_function_definitions_body(abi_functions_data):
    lines = [abi_input_to_func_defintion(row) for row in abi_functions_data]
    lines.sort(key=lines_sorter)
    return "\n".join(lines)


def get_events_definitions_body(events):
    lines = process_all_events(events)
    lines.sort(key=lines_sorter)
    return "\n".join(lines)


def lines_sorter(func_def):
    func_name = func_def.split(" ")[1]
    return func_name


def generate_all_interfaces(args, config=None):
    if not args:
        return
    if args == ["all"]:
        files = [f for f in BROWNIE_BUILD_PATH.iterdir() if f.is_file()]
        for f in files:
            generate_interface_document_from_json(json.load(open(f, "r")))
    else:
        for arg in args:
            try:
                generate_interface_document_from_json(
                    json.load(open(str(BROWNIE_BUILD_PATH / arg) + ".json", "r"))
                )
            except FileNotFoundError as e:
                raise e


if __name__ == "__main__":
    generate_all_interfaces(sys.argv[1:])
