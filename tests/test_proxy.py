from relecteur.proxy import with_tool_choice

SEARCH_TOOL = {"type": "function", "function": {"name": "code_search", "parameters": {}}}


def test_a_request_sending_tools_without_choosing_asks_for_tool_calls():
    body = {"model": "deepseek-v4-flash-0731", "messages": [], "tools": [SEARCH_TOOL]}

    assert with_tool_choice(body) == {**body, "tool_choice": "auto"}


def test_a_request_choosing_how_to_call_tools_keeps_its_choice():
    body = {"messages": [], "tools": [SEARCH_TOOL], "tool_choice": "required"}

    assert with_tool_choice(body) == body


def test_a_request_without_tools_is_left_without_tool_choice():
    body = {"model": "deepseek-v4-flash-0731", "messages": []}

    assert with_tool_choice(body) == body
