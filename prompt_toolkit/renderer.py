"""
Renders the command line on the console.
(Redraws parts of the input line that were changed.)
"""
from __future__ import unicode_literals
import sys
import six

from .utils import get_size
from .libs.wcwidth import wcwidth
from collections import defaultdict

from pygments.formatters.terminal256 import Terminal256Formatter, EscapeSequence
from pygments.styles.default import DefaultStyle
from pygments.token import Token

# Global variable to keep the colour table in memory.
_tf = Terminal256Formatter()

__all__ = (
    'RenderContext',
    'Renderer',
)

class TerminalCodes:
    """
    Escape codes for a VT100 terminal.

    For more info, see: http://www.termsys.demon.co.uk/vtansi.htm
    """
    #: Erases the screen with the background colour and moves the cursor to home.
    ERASE_SCREEN = '\x1b[2J'

    #: Erases from the current cursor position to the end of the current line.
    ERASE_END_OF_LINE = '\x1b[K'

    #: Erases the screen from the current line down to the bottom of the screen.
    ERASE_DOWN = '\x1b[J'

    CARRIAGE_RETURN = '\r'
    NEWLINE = '\n'
    CRLF = '\r\n'

    HIDE_CURSOR = '\x1b[?25l'
    DISPLAY_CURSOR = '\x1b[?25h'

    @staticmethod
    def CURSOR_GOTO(row=0, column=0):
        """ Move cursor position. """
        return '\x1b[%i;%iH' % (row, column)

    @staticmethod
    def CURSOR_UP(amount):
        if amount == 1:
            return '\x1b[A'
        else:
            return '\x1b[%iA' % amount

    @staticmethod
    def CURSOR_DOWN(amount):
        if amount == 1:
            return '\x1b[B'
        else:
            return '\x1b[%iB' % amount

    @staticmethod
    def CURSOR_FORWARD(amount):
        if amount == 1:
            return '\x1b[C'
        else:
            return '\x1b[%iC' % amount

    @staticmethod
    def CURSOR_BACKWARD(amount):
        if amount == 1:
            return '\x1b[D'
        else:
            return '\x1b[%iD' % amount


class Char(object):
    def __init__(self, char=' ', style=None): # TODO: add __slots__
        self.char = char
        self.style = style # TODO: maybe we should still use `token` instead of
                           #       `style` and use the actual style in the last step of the renderer.

    def output(self):
        """ Return the output to write this character to the terminal. """
        style = self.style

        if style:
            e = EscapeSequence(
                    fg=(_tf._color_index(style['color']) if style['color'] else None),
                    bg=(_tf._color_index(style['bgcolor']) if style['bgcolor'] else None),
                    bold=style.get('bold', False),
                    underline=style.get('underline', False))

            return ''.join([
                    e.color_string(),
                    self.char,
                    e.reset_string()
                ])
        else:
            return self.char

    @property
    def width(self):
        return max(1, wcwidth(self.char))


class Screen(object):
    """
    Two dimentional buffer for the output.

    :param style: Pygments style.
    :param grayed: True when all tokes should be replaced by `Token.Aborted`
    """
    def __init__(self, style, columns, grayed=False):
        self._buffer = defaultdict(lambda: defaultdict(Char))
        self._cursor_mappings = { } # Map (row, col) of input data to (row, col) screen output.
        self._x = 0
        self._y = 0

        self._input_row = 0
        self._input_col = 0

        self._columns = columns
        self._style = style
        self._grayed = grayed
        self._second_line_prefix_func = None

    def save_input_pos(self):
        self._cursor_mappings[self._input_row, self._input_col] = (self._y, self._x)

    def set_second_line_prefix(self, func):
        """
        Set a function that returns a list of (token,text) tuples to be
        inserted after every newline.
        """
        self._second_line_prefix_func = func

    def write_char(self, char, token, is_input=True):
        """
        Write char to current cursor position and move cursor.
        """
        assert len(char) == 1

        char_width = wcwidth(char)

        # In case of a double width character, if there is no more place left
        # at this line, go first to the following line.
        if self._x + char_width >= self._columns:
            self._y += 1
            self._x = 0

        # Remember at which position this input character has been drawn.
        if is_input:
            self.save_input_pos()

        # If grayed, replace token
        if self._grayed:
            token = Token.Aborted

        # Insertion of newline
        if char == '\n':
            self._y += 1
            self._x = 0

            if is_input:
                self._input_row += 1
                self._input_col = 0

                if self._second_line_prefix_func:
                    self.write_highlighted(self._second_line_prefix_func(), is_input=False)

        # Insertion of a 'visible' character.
        else:
            # Get style
            try:
                style = self._style.style_for_token(token)
            except KeyError:
                style = None

            # Add char to buffer
            self._buffer[self._y][self._x] = Char(char=char, style=style)

            # Move cursor position
            if is_input:
                self._input_col += 1

            if self._x + char_width >= self._columns:
                self._y += 1
                self._x = 0
            else:
                self._x += char_width

    def write_highlighted(self, data, is_input=True):
        """
        Write (Token, text) tuples to the screen.
        """
        for token, text in data:
            for c in text:
                self.write_char(c, token=token, is_input=is_input)

    def highlight_line(self, row, bgcolor='f8f8f8'):
        for (y, x), (screen_y, screen_x) in self._cursor_mappings.items():
            if y == row:
                self.highlight_character(y, x, bgcolor=bgcolor)

    def highlight_character(self, row, column, bgcolor=None, color=None):
        """
        Highlight the character at row/column position.
        (Row and column are input coordinates, not screen coordinates.)
        """
        # We can only highlight this row/column when this position has been
        # drawn to the screen. Only then we know the absolute position.
        if (row, column) in self._cursor_mappings:
            screen_y, screen_x = self._cursor_mappings[row, column]

            # Only highlight if we have this character in the buffer.
            if screen_x in self._buffer[screen_y]:
                c = self._buffer[screen_y][screen_x]
                if c.style:
                    if bgcolor: c.style['bgcolor'] = bgcolor
                    if color: c.style['color'] = color
                else:
                    c.style = {
                            'bgcolor': bgcolor,
                            'color': color,
                            }

    def output(self):
        result = []

        rows = max(self._buffer.keys()) + 1

        for y, r in enumerate(range(0, rows)):
            line_data = self._buffer[r]
            if line_data:
                cols = max(line_data.keys()) + 1

                c = 0
                while c < cols:
                    result.append(line_data[c].output())
                    c += line_data[c].width

            if y != rows - 1:
                result.append(TerminalCodes.CRLF)

        return ''.join(result)


class Renderer(object):
    highlight_current_line = False
    screen_cls = Screen

    def __init__(self, stdout=None, style=None):
        self._stdout = (stdout or sys.stdout)
        self._style = style or DefaultStyle

        # Reset position
        self._lines_in_use = 0
        self._cursor_line = 0

    def get_width(self):
        rows, cols = get_size(self._stdout.fileno())
        return cols

    def  _get_new_screen(self, render_context):
        screen = self.screen_cls(style=self._style, columns=self.get_width(), grayed=render_context.abort)

        # Write prompt.
        prompt_tuples = list(render_context.prompt.get_prompt())
        screen.write_highlighted(prompt_tuples, is_input=False)

        # Set second line prefix
        second_line_prompt = list(render_context.prompt.get_second_line_prefix())
        screen.set_second_line_prefix(lambda: second_line_prompt)

        # Write code object.
        screen.write_highlighted(render_context.code_obj.get_tokens())
        screen.save_input_pos()

        # Write help text.
        screen.set_second_line_prefix(None)
        if not (render_context.accept or render_context.abort):
            help_tokens = render_context.prompt.get_help_tokens()
            if help_tokens:
                screen.write_highlighted(help_tokens)

        # Highlight current line.
        if self.highlight_current_line and not (render_context.accept or render_context.abort):
            screen.highlight_line(render_context.code_obj.document.cursor_position_row)

        # Highlight regions
        if render_context.highlight_regions:
            for (start_row, start_column), (end_row, end_column) in render_context.highlight_regions:
                for i in range(start_column, end_column):
                    screen.highlight_character(start_row-1, i, bgcolor='444444', color='eeeeee')

        return screen

    def _render_to_str(self, render_context):
        output = []
        write = output.append

        # Move the cursor to the first line that was printed before
        # and erase everything below it.
        if self._cursor_line:
            write(TerminalCodes.CURSOR_UP(self._cursor_line))

        write(TerminalCodes.CARRIAGE_RETURN)
        write(TerminalCodes.ERASE_DOWN)

        # Generate the output of the new screen.
        screen = self._get_new_screen(render_context)
        write(screen.output())

        # Move cursor to correct position.
        if render_context.accept or render_context.abort:
            self._lines_in_use = 0
            self._cursor_line = 0
            write(TerminalCodes.CRLF)
        else:
            cursor_y, cursor_x = screen._cursor_mappings[
                            render_context.code_obj.document.cursor_position_row,
                            render_context.code_obj.document.cursor_position_col]

            if screen._y - cursor_y:
                write(TerminalCodes.CURSOR_UP(screen._y - cursor_y))
            if screen._x > cursor_x:
                write(TerminalCodes.CURSOR_BACKWARD(screen._x - cursor_x))
            if screen._x < cursor_x:
                write(TerminalCodes.CURSOR_FORWARD(cursor_x - screen._x))

            self._lines_in_use = screen._y
            self._cursor_line = cursor_y

        return ''.join(output)

    def render(self, render_context):
        out = self._render_to_str(render_context)
        self._stdout.write(out)
        self._stdout.flush()

    def render_completions(self, completions):
        self._stdout.write(TerminalCodes.CRLF)
        for line in self._in_columns([ c.display for c in completions ]):
            self._stdout.write('%s\r\n' % line)

        return
        if many: # TODO: Implement paging
            'Display all %i possibilities? (y on n)'

    def clear(self):
        """
        Clear screen and go to 0,0
        """
        self._stdout.write(TerminalCodes.ERASE_SCREEN)
        self._stdout.write(TerminalCodes.CURSOR_GOTO(0, 0))

    def _in_columns(self, item_iterator, margin_left=0): # XXX: copy of deployer.console.in_columns
        """
        :param item_iterator: An iterable, which yields either ``basestring``
                              instances, or (colored_item, length) tuples.
        """
        # Helper functions for extracting items from the iterator
        def get_length(item):
            return len(item) if isinstance(item, six.string_types) else item[1]

        def get_text(item):
            return item if isinstance(item, six.string_types) else item[0]

        # First, fetch all items
        all_items = list(item_iterator)

        if not all_items:
            return

        # Calculate the longest.
        max_length = max(map(get_length, all_items)) + 1

        # World per line?
        term_width = self.get_width() - margin_left
        words_per_line = int(max(term_width / max_length, 1))

        # Iterate through items.
        margin = ' ' * margin_left
        line = [ margin ]
        for i, j in enumerate(all_items):
            # Print command and spaces
            line.append(get_text(j))

            # When we reached the max items on this line, yield line.
            if (i+1) % words_per_line == 0:
                yield ''.join(line)
                line = [ margin ]
            else:
                # Pad with whitespace
                line.append(' ' * (max_length - get_length(j)))

        yield ''.join(line)
