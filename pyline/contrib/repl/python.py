"""
Utility for creating a Python repl.

::

    from pyline.contrib.python import PythonCommandLine
    cli = PythonCommandLine()
    cli.read_input()

"""
from __future__ import print_function

from pygments import highlight
from pygments.formatters.terminal256  import Terminal256Formatter
from pygments.lexers import PythonLexer, PythonTracebackLexer
from pygments.style import Style
from pygments.token import Keyword, Operator, Number, Name, Error, Comment, Token

from pyline import CommandLine
from pyline.code import Completion, Code
from pyline.inputstream_handler import ViInputStreamHandler, EmacsInputStreamHandler
from pyline.line import Exit
from pyline.line import Line
from pyline.prompt import Prompt

from six import exec_

import jedi
import os
import re
import traceback

__all__ = ('PythonCommandLine', 'embed')


class PythonStyle(Style):
    background_color = None
    styles = {
        Keyword:                      '#ee00ee',
        Operator:                     '#aa6666',
        Number:                       '#ff0000',
        Name:                         '#008800',
        Token.Literal.String:         '#440000',

        Error:                        '#000000 bg:#ff8888',
        Comment:                      '#0000dd',
        Token.Bash:                   '#333333',
        Token.IPython:                '#660066',

        # Signature highlighting.
        Token.Signature:             '#888888',
        Token.Signature.Operator:    'bold #888888',
        Token.Signature.CurrentName: 'bold underline #888888',

        # Highlighting for the reverse-search prompt.
        Token.Prompt:                  'bold #004400',
        Token.Prompt.ISearch.Bracket:  'bold #440000',
        Token.Prompt.ISearch:          '#550000',
        Token.Prompt.ISearch.Backtick: 'bold #550033',
        Token.Prompt.ISearch.Text:     'bold',
        Token.Prompt.SecondLinePrefix: 'bold #888888',
        Token.Prompt.ArgText:          'bold',

        Token.Toolbar:         'bg:#444444 #aaaaaa',
        Token.Toolbar.Off:     'bg:#444444 #888888',
        Token.Toolbar.On:      'bg:#444444 #ffffff',
        Token.Toolbar.Mode:    'bg:#444444 #ffffaa',

        # Grayed
        Token.Aborted:    '#aaaaaa',
    }


class _PythonInputStreamHandlerMixin(object):
    """
    Extensions to the input stream handler for custom 'enter' behaviour.
    """
    def F6(self):
        """ Enable/Disable paste mode. """
        self._line.paste_mode = not self._line.paste_mode
        if self._line.paste_mode:
            self._line.multiline = True

    def F7(self):
        self._line.multiline = not self._line.multiline

    def enter(self):
        self._enable_multiline_on_enter()
        super(_PythonInputStreamHandlerMixin, self).enter()

    def _enable_multiline_on_enter(self):
        """
        (Temporarily) enable multiline when pressing enter.
        When:
        - We press [enter] after a color or backslash (line continuation).
        - After unclosed brackets.
        """
        def is_empty_or_space(s):
            return s == '' or s.isspace()
        cursor_at_the_end = self._line.document.cursor_at_the_end

        # If we just typed a colon, or still have open brackets, always insert a real newline.
        if cursor_at_the_end and (self._line._colon_before_cursor() or
                                  self._line._has_unclosed_brackets()):
            self._line.multiline = True

        # If the character before the cursor is a backslash (line continuation
        # char), insert a new line.
        elif cursor_at_the_end and (self._line.document.text_before_cursor[-1:] == '\\'):
            self._line.multiline = True


class PythonViInputStreamHandler(_PythonInputStreamHandlerMixin, ViInputStreamHandler):
    def enter(self):
        self._enable_multiline_on_enter()

        if self._line.multiline:
            if self._vi_navigation_mode:
                # We are in VI-navigation mode after pressing `Alt`.
                self._line.return_input()
            else:
                self._line.newline()
        else:
            # In single line input, always execute when pressing enter.
            self._line.return_input()


class PythonEmacsInputStreamHandler(_PythonInputStreamHandlerMixin, EmacsInputStreamHandler):
    def enter(self):
        self._enable_multiline_on_enter()

        if self._line.multiline:
            self._line.newline()
        else:
            # In single line input, always execute when pressing enter.
            self._line.return_input()

    def alt_enter(self):
        self._line.return_input()


class PythonLine(Line):
    """
    Custom `Line` class with some helper functions.
    """
    def reset(self):
        super(PythonLine, self).reset()

        #: Boolean `paste` flag. If True, don't insert whitespace after a
        #: newline.
        self.paste_mode = False

        #: Boolean `multiline` flag. If True, [Enter] will always insert a
        #: newline, and it is required to use [Alt+Enter] execute commands.
        self.multiline = False

    def set_text(self, value, safe_current_in_undo_buffer=True):
        super(PythonLine, self).set_text(value, safe_current_in_undo_buffer)

        if '\n' in value:
            self.multiline = True

    def _colon_before_cursor(self):
        return self.document.text_before_cursor[-1:] == ':'

    def _has_unclosed_brackets(self):
        """ Starting at the end of the string. If we find an opening bracket
        for which we didn't had a closing one yet, return True. """
        text = self.document.text_before_cursor
        stack = []

        # Ignore braces inside strings
        text = re.sub(r'''('[^']*'|"[^"]*")''', '', text) # XXX: handle escaped quotes.!

        for c in reversed(text):
            if c in '])}':
                stack.append(c)

            elif c in '[({':
                if stack:
                    if ((c == '[' and stack[-1] == ']') or
                        (c == '{' and stack[-1] == '}') or
                        (c == '(' and stack[-1] == ')')):
                        stack.pop()
                else:
                    # Opening bracket for which we didn't had a closing one.
                    return True

        return False

    def newline(self):
        r"""
        Insert \n at the cursor position. Also add necessary padding.
        """
        insert_text = super(PythonLine, self).insert_text

        if self.paste_mode:
            insert_text('\n')
        else:
            # Go to new line, but also add indentation.
            current_line = self.document.current_line_before_cursor.rstrip()
            insert_text('\n')

            # Copy whitespace from current line
            for c in current_line:
                if c.isspace():
                    insert_text(c)
                else:
                    break

            # If the last line ends with a colon, add four extra spaces.
            if current_line[-1:] == ':':
                for x in range(4):
                    insert_text(' ')


class PythonPrompt(Prompt):
    def __init__(self, line, code, pythonline):
        super(PythonPrompt, self).__init__(line, code)
        self._pythonline = pythonline

    @property
    def _prefix(self):
        return (Token.Prompt, 'In [%s]' % self._pythonline.current_statement_index)

    def get_default_prompt(self):
        yield self._prefix
        yield (Token.Prompt, ': ')

    def get_isearch_prompt(self):
        yield self._prefix
        for t in super(PythonPrompt, self).get_isearch_prompt():
            yield t

    def get_arg_prompt(self, text):
        yield self._prefix
        for t in super(PythonPrompt, self).get_arg_prompt(text):
            yield t

    def get_help_tokens(self):
        """
        When inside functions, show signature.
        """
        result = []
        result.extend(self._get_signature_tokens())
        result.extend(self._get_toolbar_tokens())
        return result

    def _get_signature_tokens(self):
        result = []
        append = result.append
        script = self.code._get_jedi_script()
        Signature = Token.Signature

        # Show signatures in help text.
        try:
            signatures = script.call_signatures()
        except ValueError:
            # e.g. in case of an invalid \x escape.
            signatures = []

        if signatures:
            sig = signatures[0] # Always take the first one.

            append((Token, '\n           '))
            append((Signature, sig.full_name))
            append((Signature.Operator, '('))

            for i, p in enumerate(sig.params):
                if i == sig.index:
                    append((Signature.CurrentName, str(p.name)))
                else:
                    append((Signature, str(p.name)))
                append((Signature.Operator, ', '))

            result.pop() # Pop last comma
            append((Signature.Operator, ')'))
        else:
            append((Token, '\n'))

        return result

    def _get_toolbar_tokens(self):
        result = []
        append = result.append
        TB = Token.Toolbar

        append((Token, '\n  '))
        append((TB, '  '))

        if self._pythonline.vi_mode and self._pythonline._inputstream_handler._vi_navigation_mode:
            append((TB.Mode, '(vi-NAV)'))
            append((TB, '    '))
        elif self._pythonline.vi_mode:
            append((TB.Mode, '(vi-INSERT)'))
            append((TB, ' '))
        else:
            append((TB.Mode, '(emacs)'))
            append((TB, ' '))

        if self.line.paste_mode:
            append((TB.On, '[F6] Paste mode. (on)  '))
        else:
            append((TB.Off, '[F6] Paste mode. (off) '))

        if self.line.multiline:
            append((TB.On, '[F7] Multiline (on)  '))
        else:
            append((TB.Off, '[F7] Multiline (off) '))

        if self.line.multiline:
            append((TB, '[Alt+Enter] Execute.'))
        else:
            append((TB, '                    '))
        append((TB, '  '))

        return result


class PythonCode(Code):
    lexer_cls = PythonLexer

    def __init__(self, document, globals, locals):
        self._globals = globals
        self._locals = locals
        super(PythonCode, self).__init__(document)

    def _get_tokens(self):
        """ Overwrite parent function, to change token types of non-matching
        brackets to Token.Error for highlighting. """
        result = super(PythonCode, self)._get_tokens()

        stack = [] # Pointers to the result array

        for index, (token, text) in enumerate(result):
            top = result[stack[-1]][1] if stack else ''

            if text in '({[]})':
                if text in '({[':
                    # Put open bracket on the stack
                    stack.append(index)

                elif (text == ')' and top == '(' or
                      text == '}' and top == '{' or
                      text == ']' and top == '['):
                    # Match found
                    stack.pop()
                else:
                    # No match for closing bracket.
                    result[index] = (Token.Error, text)

        # Highlight unclosed tags that are still on the stack.
        for index in stack:
            result[index] = (Token.Error, result[index][1])

        return result

    def _get_jedi_script(self):
        return jedi.Interpreter(self.text,
                column=self.document.cursor_position_col,
                line=self.document.cursor_position_row,
                path='input-text',
                namespaces=[ self._locals, self._globals ])

    def get_completions(self, recursive=False):
        """ Ask jedi to complete. """
        script = self._get_jedi_script()

        for c in script.completions():
            yield Completion(c.name, c.complete)


class PythonCommandLine(CommandLine):
    line_cls = PythonLine
    style_cls = PythonStyle

    @property
    def inputstream_handler_cls(self):
        if self.vi_mode:
            return PythonViInputStreamHandler
        else:
            return PythonEmacsInputStreamHandler

    def __init__(self, globals=None, locals=None, vi_mode=False, stdin=None, stdout=None):
        self.globals = globals or {}
        self.globals.update({ k: getattr(__builtins__, k) for k in dir(__builtins__) })
        self.locals = locals or {}

        self.vi_mode = vi_mode

        #: Incremeting integer counting the current statement.
        self.current_statement_index = 1

        # The `PythonCode` needs a reference back to this class in order to do
        # autocompletion on the globals/locals.
        self.code_cls = lambda document: PythonCode(document, self.globals, self.locals)

        # The `PythonPrompt` class needs a reference back in order to show the
        # input method.
        self.prompt_cls = lambda line, code: PythonPrompt(line, code, self)

        super(PythonCommandLine, self).__init__(stdin=stdin, stdout=stdout)

    def start_repl(self):
        """
        Start the Read-Eval-Print Loop.
        """
        try:
            while True:
                # Read
                document = self.read_input()
                line = document.text

                try:
                    # Eval and print.
                    self._execute(line)
                except KeyboardInterrupt as e: # KeyboardInterrupt doesn't inherit from Exception.
                    self._handle_keyboard_interrupt(e)
                except Exception as e:
                    self._handle_exception(e)

                self.current_statement_index += 1
        except Exit:
            pass

    def _execute(self, line):
        """
        Evaluate the line and print the result.
        """
        if line[0:1] == '!':
            # Run as shell command
            os.system(line[1:])
        else:
            # Try eval first
            try:
                result = eval(line, self.globals, self.locals)
                self.locals['_'] = self.locals['_%i' % self.current_statement_index] = result
                if result is not None:
                    print('Out[%i]: %r' % (self.current_statement_index, result))
            # If not a valid `eval` expression, run using `exec` instead.
            except SyntaxError:
                exec_(line, self.globals, self.locals)

            print()

    def _handle_exception(self, e):
        tb = traceback.format_exc()
        print(highlight(tb, PythonTracebackLexer(), Terminal256Formatter()))
        print(e)

    def _handle_keyboard_interrupt(self, e):
        print('\rKeyboardInterrupt')


def embed(globals=None, locals=None, vi_mode=False):
    PythonCommandLine(globals, locals, vi_mode=vi_mode).start_repl()
