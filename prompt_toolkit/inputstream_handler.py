"""
An :class:`~.InputStreamHandler` receives callbacks for the keystrokes parsed
from the input in the :class:`~prompt_toolkit.inputstream.InputStream`
instance.

The `InputStreamHandler` will according to the implemented keybindings apply
the correct manipulations on the :class:`~prompt_toolkit.line.Line` object.

This module implements Vi and Emacs keybindings.
"""
from __future__ import unicode_literals
from .line import ReturnInput, Abort, ClipboardData, ClipboardDataType

__all__ = (
    'InputStreamHandler',
    'EmacsInputStreamHandler',
    'ViInputStreamHandler'
)


class InputStreamHandler(object):
    """
    This is the base class for :class:`~.EmacsInputStreamHandler` and
    :class:`~.ViInputStreamHandler`. It implements the common keybindings.

    :attr line: :class:`~prompt_toolkit.line.Line` class.
    """
    def __init__(self, line):
        self._line = line
        self._reset()

    def _reset(self):
        #: True when the user pressed on the 'tab' key.
        self._second_tab = False

        #: The name of the last previous public function call.
        self._last_call = None

        self.__arg_count = None

    @property
    def _arg_count(self):
        """ 'arg' count. For command repeats. """
        return self.__arg_count

    @_arg_count.setter
    def _arg_count(self, value):
        self.__arg_count = value

        # Set argument prompt
        if value:
            self._line.set_arg_prompt(value)
        else:
            self._line.set_arg_prompt('')

    def __call__(self, name, *a):
        if name != 'ctrl_i':
            self._second_tab = False

        # Call actual handler
        method = getattr(self, name, None)
        if method:
            try:
                method(*a)
            except (Abort, ReturnInput):
                # Reset state when the input has been accepted/aborted.
                self._reset()
                raise

        # Keep track of what the last called method was.
        if not name.startswith('_'):
            self._last_call = name

    def home(self):
        self._line.home()

    def end(self):
        self._line.end()

    # CTRL keys.

    def ctrl_a(self):
        self._line.cursor_to_start_of_line()

    def ctrl_b(self):
        self._line.cursor_left()

    def ctrl_c(self):
        self._line.abort()

    def ctrl_d(self):
        self._line.exit()

    def ctrl_e(self):
        self._line.cursor_to_end_of_line()

    def ctrl_f(self):
        self._line.cursor_right()

    def ctrl_g(self):
        """ Abort an incremental search and restore the original line """
        self._line.exit_isearch(restore_original_line=True)

    def ctrl_h(self):
        self._line.delete_character_before_cursor()

    def ctrl_i(self):
        r""" Ctrl-I is identical to "\t" """
        self.tab()

    def ctrl_j(self):
        """ Newline."""
        self.enter()

    def ctrl_k(self):
        data = ClipboardData(self._line.delete_until_end_of_line())
        self._line.set_clipboard(data)

    def ctrl_l(self):
        self._line.clear()

    def ctrl_m(self):
        """ Carriage return """
        # Alias for newline.
        self.ctrl_j()

    def ctrl_n(self):
        self._line.history_forward()

    def ctrl_o(self):
        pass

    def ctrl_p(self):
        self._line.history_backward()

    def ctrl_q(self):
        pass

    def ctrl_r(self):
        self._line.reverse_search()

    def ctrl_s(self):
        self._line.forward_search()

    def ctrl_t(self):
        self._line.swap_characters_before_cursor()

    def ctrl_u(self):
        """
        Clears the line before the cursor position. If you are at the end of
        the line, clears the entire line.
        """
        self._line.delete_from_start_of_line()

    def ctrl_v(self):
        pass

    def ctrl_w(self):
        """
        Delete the word before the cursor.
        """
        for i in range(self._arg_count or 1):
            self._line.delete_word_before_cursor()

    def ctrl_x(self):
        pass

    def ctrl_y(self):
        # Pastes the clipboard content.
        self._line.paste_from_clipboard()

    def ctrl_z(self):
        pass

    def page_up(self):
        self._line.history_backward()

    def page_down(self):
        self._line.history_forward()

    def arrow_left(self):
        self._line.cursor_left()

    def arrow_right(self):
        self._line.cursor_right()

    def arrow_up(self):
        self._line.auto_up()

    def arrow_down(self):
        self._line.auto_down()

    def backspace(self):
        self._line.delete_character_before_cursor()

    def delete(self):
        self._line.delete()

    def tab(self):
        """
        Autocomplete.
        """
        if self._second_tab:
            self._line.list_completions()
            self._second_tab = False
        else:
            self._second_tab = not self._line.complete()

    def insert_char(self, data, overwrite=False):
        """ Insert data at cursor position.  """
        assert len(data) == 1

        # Don't create an entry in the history buffer for every single typed
        # character. (Undo should undo multiple typed characters at once.)
        safe = self._last_call != 'insert_char'

        self._line.insert_text(data, overwrite=overwrite, safe_current_in_undo_buffer=safe)

    def enter(self):
        self._line.return_input()

    def alt_enter(self): # ESC-enter should always accept. -> enter in VI
                         # insert mode should insert a newline. For emacs not
                         # sure yet.
        self._line.newline()


class EmacsInputStreamHandler(InputStreamHandler):
    """
    Some e-macs extensions.
    """
    # Overview of Readline emacs commands:
    # http://www.catonmat.net/download/readline-emacs-editing-mode-cheat-sheet.pdf

    def _reset(self):
        super(EmacsInputStreamHandler, self)._reset()
        self._escape_pressed = False
        self._ctrl_x_pressed = False

    def escape(self):
        # Escape is the same as the 'alt-' prefix.
        self._escape_pressed = True

    def ctrl_x(self):
        self._ctrl_x_pressed = True

    def __call__(self, name, *a):
        reset_arg_count_after_call = True

        # When escape was pressed, call the `alt_`-function instead.
        # (This is emacs-mode behaviour. The alt-prefix is equal to the escape
        # key, and in VI mode, that's used to go from insert to navigation mode.)
        if self._escape_pressed:
            if name == 'insert_char':
                # Handle Alt + digit in the `alt_digit` method.
                if a[0] in '0123456789' or (a[0] == '-' and self._arg_count == None):
                    name = 'alt_digit'
                    reset_arg_count_after_call = False

                # Handle Alt + char in their respective `alt_X` method.
                else:
                    name = 'alt_' + a[0]
                    a = []
            else:
                name = 'alt_' + name
            self._escape_pressed = False

        # If Ctrl-x was pressed. Prepend ctrl_x prefix to hander name.
        if self._ctrl_x_pressed:
            name = 'ctrl_x_%s' % name

        super(EmacsInputStreamHandler, self).__call__(name, *a)

        # Reset arg count.
        if name == 'escape':
            reset_arg_count_after_call = False

        if reset_arg_count_after_call:
            self._arg_count = None

        # Reset _ctrl_x_pressed state.
        if name != 'ctrl_x':
            self._ctrl_x_pressed = False

    def insert_char(self, data, overwrite=False):
        for i in range(self._arg_count or 1):
            super(EmacsInputStreamHandler, self).insert_char(data, overwrite=overwrite)

    def alt_ctrl_j(self):
        """ ALT + Newline """
        # Alias for alt_enter
        self.alt_enter()

    def alt_ctrl_m(self):
        """ ALT + Carriage return """
        # Alias for alt_enter
        self.alt_enter()

    def alt_digit(self, digit):
        """ ALT + digit or '-' pressed. """
        self._arg_count = _arg_count_append(self._arg_count, digit)

    def alt_enter(self):
        pass

    def alt_c(self):
        """
        Capitalize the current (or following) word.
        """
        words = self._line.document.get_following_words(self._arg_count or 1, consume_nonword_before=True)
        self._line.insert_text(words.capitalize(), overwrite=True)

    def alt_f(self):
        self._line.cursor_word_forward()

    def alt_b(self):
        self._line.cursor_word_back()

    def alt_d(self):
        """
        Delete the Word after the cursor.
        """
        data = ClipboardData(self._line.delete_word())
        self._line.set_clipboard(data)

    def alt_l(self):
        """
        Lowercase the current (or following) word.
        """
        words = self._line.document.get_following_words(self._arg_count or 1, consume_nonword_before=True)
        self._line.insert_text(words.lower(), overwrite=True)

    def alt_t(self):
        """
        Swap the last two words before the cursor.
        """
        # TODO

    def alt_u(self):
        """
        Uppercase the current (or following) word.
        """
        words = self._line.document.get_following_words(self._arg_count or 1,
                                        consume_nonword_before=True)
        self._line.insert_text(words.upper(), overwrite=True)

    def ctrl_underscore(self):
        """
        Undo.
        """
        self._line.undo()

    def alt_backslash(self):
        """
        Delete all spaces and tabs around point.
        (delete-horizontal-space)
        """

    def alt_star(self):
        """
        `alt-*`: Insert all possible completions of the preceding text.
        """

    def ctrl_x_ctrl_e(self):
        """
        Open editor.
        """
        self._line.open_in_editor()

    def ctrl_x_ctrl_u(self):
        self._line.undo()

    def ctrl_x_ctrl_x(self):
        """
        Move cursor back and forth between the start and end of the current
        line.
        """
        if self._line.document.current_char == '\n':
            self._line.cursor_to_start_of_line(after_whitespace=False)
        else:
            self._line.cursor_to_end_of_line()


class ViMode(object):
    NAVIGATION = 'navigation'
    INSERT = 'insert'
    REPLACE = 'replace'


class ViInputStreamHandler(InputStreamHandler):
    """
    Vi extensions.

    # Overview of Readline Vi commands:
    # http://www.catonmat.net/download/bash-vi-editing-mode-cheat-sheet.pdf
    """
    # TODO: In case of navigation mode, we should not be able to move the
    # cursor after the last character of a line.
    def _reset(self):
        super(ViInputStreamHandler, self)._reset()
        self._vi_mode = ViMode.INSERT
        self._all_navigation_handles = self._get_navigation_mode_handles()

        # Hook for several actions in navigation mode which require an
        # additional key to be typed before they execute.
        self._one_character_callback = None

    def escape(self):
        """ Escape goes to vi navigation mode. """
        self._vi_mode = ViMode.NAVIGATION
        self._current_handles = self._all_navigation_handles

        # Reset arg count.
        self._arg_count = None

    def enter(self):
        if self._vi_mode == ViMode.NAVIGATION:
            self._line.return_input()
        else:
            self._line.newline()

    def ctrl_v(self):
        # TODO: Insert a character literally (quoted insert).
        pass

    def _get_navigation_mode_handles(self):
        """
        Create a dictionary that maps the vi key binding to their handlers.
        """
        handles = {}
        line = self._line

        def handle(key):
            """ Decorator that registeres the handler function in the handles dict. """
            def wrapper(func):
                handles[key] = func
                return func
            return wrapper

        # List of navigation commands: http://hea-www.harvard.edu/~fine/Tech/vi.html

        @handle('a')
        def _(arg):
            self._vi_mode = ViMode.INSERT
            line.cursor_right()

        @handle('A')
        def _(arg):
            self._vi_mode = ViMode.INSERT
            line.cursor_to_end_of_line()

        @handle('b') # Move one word or token left.
        @handle('B') # Move one non-blank word left ((# TODO: difference between 'b' and 'B')
        def _(arg):
            for i in range(arg):
                line.cursor_word_back()

        @handle('C')
        @handle('c$')
        def _(arg):
            # Change to end of line.
            data = ClipboardData(line.delete_until_end_of_line())
            line.set_clipboard(data)
            self._vi_mode = ViMode.INSERT

        @handle('cc')
        @handle('S')
        def _(arg):
            # TODO: Change current line (equivalent to 0c$).
            pass

        @handle('cw')
        @handle('ce')
        def _(arg):
            data = ClipboardData(''.join(line.delete_word() for i in range(arg)))
            line.set_clipboard(data)
            self._vi_mode = ViMode.INSERT

        @handle('D')
        def _(arg):
            data = ClipboardData(line.delete_until_end_of_line())
            line.set_clipboard(data)

        @handle('dd')
        def _(arg):
            text = '\n'.join(line.delete_current_line() for i in range(arg))
            data = ClipboardData(text, ClipboardDataType.LINES)
            line.set_clipboard(data)

        @handle('d$')
        def _(arg):
            # Delete until end of line.
            data = ClipboardData(line.delete_until_end_of_line())
            line.set_clipboard(data)

        @handle('dw')
        def _(arg):
            data = ClipboardData(''.join(line.delete_word() for i in range(arg)))
            line.set_clipboard(data)

        @handle('e') # Move to the end of the current word
        @handle('E') # Move to the end of the current non-blank word. (# TODO: diff between 'e' and 'E')
        def _(arg):
            # End of word
            line.cursor_to_end_of_word()

        @handle('f')
        def _(arg):
            # Go to next occurance of character. Typing 'fx' will move the
            # cursor to the next occurance of character. 'x'.
            def cb(char):
                for i in range(arg):
                    line.go_to_character_in_line(char)
            self._one_character_callback = cb

        @handle('F')
        def _(arg):
            # Go to previous occurance of character. Typing 'Fx' will move the
            # cursor to the previous occurance of character. 'x'.
            # TODO
            pass

        @handle('G')
        def _(arg):
            # Move to the history line n (you may specify the argument n by
            # typing it on number keys, for example, 15G)
            # TODO
            pass

        @handle('h')
        def _(arg):
            for i in range(arg):
                line.cursor_left()

        @handle('H')
        def _(arg):
            # Vi moves to the start of the visible region.
            # cursor position 0 is okay for us.
            line.cursor_position = 0

        @handle('i')
        def _(arg):
            self._vi_mode = ViMode.INSERT

        @handle('I')
        def _(arg):
            self._vi_mode = ViMode.INSERT
            line.cursor_to_start_of_line()

        @handle('j')
        def _(arg):
            for i in range(arg):
                line.auto_down()

        @handle('J')
        def _(arg):
            line.join_next_line()

        @handle('k')
        def _(arg):
            for i in range(arg):
                line.auto_up()

        @handle('l')
        @handle(' ')
        def _(arg):
            for i in range(arg):
                line.cursor_right()

        @handle('L')
        def _(arg):
            # Vi moves to the start of the visible region.
            # cursor position 0 is okay for us.
            line.cursor_position = len(line.text)

        @handle('n')
        def _(arg):
            # Repeat search in the same direction as previous.
            # TODO
            pass

        @handle('N')
        def _(arg):
            # Repeat search in the opposite direction as previous.
            # TODO
            pass

        @handle('p')
        def _(arg):
            # Paste after
            for i in range(arg):
                line.paste_from_clipboard()

        @handle('P')
        def _(arg):
            # Paste before
            for i in range(arg):
                line.paste_from_clipboard(before=True)

        @handle('r')
        def _(arg):
            # Replace single character under cursor
            def cb(char):
                line.insert_text(char * arg, overwrite=True)
            self._one_character_callback = cb

        @handle('R')
        def _(arg):
            # Go to 'replace'-mode.
            self._vi_mode = ViMode.REPLACE

        @handle('s')
        def _(arg):
            # Substitute with new text
            # (Delete character(s) and go to insert mode.)
            data = ClipboardData(''.join(line.delete() for i in range(arg)))
            line.set_clipboard(data)
            self._vi_mode = ViMode.INSERT

        @handle('t')
        def _(arg):
            # Move right to the next occurance of c, then one char backward.
            def cb(char):
                for i in range(arg):
                    line.go_to_character_in_line(char)
                line.cursor_left()
            self._one_character_callback = cb

        @handle('T')
        def _(arg):
            # Move left to the previous occurance of c, then one char forward.
            # TODO
            pass

        @handle('u')
        def _(arg):
            for i in range(arg):
                line.undo()

        @handle('v')
        def _(arg):
            line.open_in_editor()

        @handle('w') # Move one word or token right.
        @handle('W') # Move one non-blank word right. (# TODO: difference between 'w' and 'W')
        def _(arg):
            for i in range(arg):
                line.cursor_word_forward()

        @handle('x')
        def _(arg):
            # Delete character.
            data = ClipboardData(''.join(line.delete() for i in range(arg)))
            line.set_clipboard(data)

        @handle('X')
        def _(arg):
            line.delete_character_before_cursor()

        @handle('yy')
        def _(arg):
            # Yank the whole line.
            text = '\n'.join(line.document.lines
                [line.document.cursor_position_row:line.document.cursor_position_row + arg])

            data = ClipboardData(text, ClipboardDataType.LINES)
            line.set_clipboard(data)

        @handle('yw')
        def _(arg):
            # Yank word.
            pass

        @handle('^')
        def _(arg):
            line.cursor_to_start_of_line(after_whitespace=True)

        @handle('0')
        def _(arg):
            # Move to the beginning of line.
            line.cursor_to_start_of_line(after_whitespace=False)

        @handle('$')
        def _(arg):
            # TODO: This should not move after but *on* the last character.
            line.cursor_to_end_of_line()

        @handle('%')
        def _(arg):
            # Move to the corresponding opening/closing bracket (()'s, []'s and {}'s).
            line.go_to_matching_bracket()

        @handle('+')
        def _(arg):
            # TODO: move to first non whitespace of next line
            pass

        @handle('-')
        def _(arg):
            # TODO: move to first non whitespace of previous line
            pass

        @handle('{')
        def _(arg):
            # TODO: Move to previous blank-line separated section.
            #while not line.current_line.isspace():
            #    line.cursor_up()
            pass

        @handle('}')
        def _(arg):
            # TODO: move to next blank-line separated section.
            pass

        @handle('>>')
        def _(arg):
            # TODO: Indent current line.
            pass

        @handle('<<')
        def _(arg):
            # TODO: Unindent current line.
            pass

        @handle('O')
        def _(arg):
            # Open line above and enter insertion mode
            line.insert_line_above()
            self._vi_mode = ViMode.INSERT

        @handle('o')
        def _(arg):
            # Open line below and enter insertion mode
            line.insert_line_below()
            self._vi_mode = ViMode.INSERT

        @handle('~')
        def _(arg):
            """ Reverse case of current character and move cursor forward. """
            c = line.document.current_char
            if c is not None and c != '\n':
                c = (c.upper() if c.islower() else c.lower())
                line.insert_text(c, overwrite=True)

        @handle('|')
        def _(arg):
            # Move to the n-th column (you may specify the argument n by typing
            # it on number keys, for example, 20|).
            # TODO
            pass

        @handle('/')
        def _(arg):
            # TODO: Search history backward for a command matching string.
            pass

        @handle('?')
        def _(arg):
            # TODO: Search history forward for a command matching string.
            pass

        return handles

    def insert_char(self, data):
        """ Insert data at cursor position.  """
        assert len(data) == 1

        if self._one_character_callback:
            self._one_character_callback(data)
            self._one_character_callback = False

        elif self._vi_mode == ViMode.NAVIGATION:
            # Always handle numberics to build the arg
            if data in '123456789' or (self._arg_count and data == '0'):
                self._arg_count = _arg_count_append(self._arg_count, data)

            # If we have a handle for the current keypress. Call it.
            elif data in self._current_handles:
                # Pass argument to handle.
                arg_count = self._arg_count
                self._arg_count = None

                self._current_handles[data](arg_count or 1)
                self._current_handles = self._all_navigation_handles

            # If there are several combitations of handles, starting with the
            # keys that were already pressed. Reduce to this subset of
            # handlers.
            elif data in [ k[0] for k in self._current_handles.keys() ]:
                self._current_handles = { k[1:]:h for k, h in self._current_handles.items() if k[0] == data }

            # No match. Reset.
            else:
                self._current_handles = self._all_navigation_handles

        # In replace/text mode.
        elif self._vi_mode == ViMode.REPLACE:
            super(ViInputStreamHandler, self).insert_char(data, overwrite=True)

        # In insert/text mode.
        elif self._vi_mode == ViMode.INSERT:
            super(ViInputStreamHandler, self).insert_char(data)


def _arg_count_append(current, data):
    """
    Utility for manupulating the arg-count string.

    :param current: int or None
    :param data: the typed digit as string
    :returns: int or None
    """
    assert data in '-0123456789'

    if current is None:
        if data == '-':
            data = '-1'
        result = int(data)
    else:
        result = int("%s%s" % (current, data))

    # Don't exceed a million.
    if int(result) >= 1000000:
        result = None

    return result
