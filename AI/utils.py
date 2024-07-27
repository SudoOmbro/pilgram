

def filter_string_list_remove_empty(target: list[str]) -> list[str]:
    result: list[str] = []
    for item in target:
        if (item == "") or (item == "\n"):
            continue
        result.append(item)
    return result


def filter_strings_list_remove_too_short(target: list[str], min_length: int) -> list[str]:
    result: list[str] = []
    for item in target:
        if len(item) < min_length:
            continue
        result.append(item)
    return result


def get_string_list_from_tuple_list(tuple_list: list[tuple], location: int) -> list[str]:
    result: list[str] = []
    for item in tuple_list:
        result.append(item[location])
    return result


def remove_leading_numbers(string: str) -> str:
    while string[0].isdigit():
        string = string.lstrip("0123456789")
    string = string.lstrip(".")
    return string
