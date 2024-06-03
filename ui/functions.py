from ui.utils import UserContext


def placeholder(context: UserContext) -> str:
    """ temporary placeholder function """
    return "hello world"


def echo(context: UserContext, text) -> str:
    try:
        username = context.get("username")
    except KeyError:
        username = "player"
    return f"{username} says: '{text}'"
