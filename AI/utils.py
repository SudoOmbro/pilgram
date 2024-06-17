from typing import List


def filter_string_list_remove_empty(target: List[str]) -> List[str]:
    result: List[str] = []
    for item in target:
        if (item == "") or (item == "\n"):
            continue
        result.append(item)
    return result


def get_string_list_from_tuple_list(tuple_list: List[tuple], location: int) -> List[str]:
    result: List[str] = []
    for item in tuple_list:
        result.append(item[location])
    return result


def remove_leading_numbers(string: str) -> str:
    while string[0].isdigit():
        string = string.lstrip("0123456789")
    string = string.lstrip(".")
    return string
