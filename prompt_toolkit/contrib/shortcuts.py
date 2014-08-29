"""
Useful shortcuts.
"""
from __future__ import unicode_literals

from .. import CommandLine, AbortAction
from ..prompt import Prompt
from ..line import Exit, Abort


def get_input(message, raise_exception_on_abort=False):
    """
    Replacement for `raw_input`.
    Ask for input, return the answer.
    This returns `None` when Ctrl-D was pressed.
    """
    class CustomPrompt(Prompt):
        default_prompt_text = message

    class CLI(CommandLine):
        prompt_cls = CustomPrompt

    cli = CLI()

    on_abort = AbortAction.RAISE_EXCEPTION if raise_exception_on_abort else AbortAction.RETURN_NONE

    code_obj = cli.read_input(on_abort=on_abort, on_exit=AbortAction.IGNORE)
    if code_obj:
        return code_obj.text