import datetime
import os

__all__ = ('History', 'FileHistory')


class History(object):
    def __init__(self):
        self.strings = []

    def append(self, string):
        self.strings.append(string)

    def __getitem__(self, key):
        return self.strings[key]

    def __len__(self):
        return len(self.strings)



class FileHistory(History):
    def __init__(self, filename):
        super(FileHistory, self).__init__()
        self.filename = filename

        self._load()

    def _load(self):
        lines = []

        def add():
            if lines:
                # Join and drop trailing newline.
                string = ''.join(lines)[:-1]

                self.strings.append(string)

        if os.path.exists(self.filename):
            with open(self.filename, 'r') as f:
                for line in f:
                    if line.startswith('+'):
                        lines.append(line[1:])
                    else:
                        add()
                        lines = []

                add()


    def append(self, string):
        super(FileHistory, self).append(string)

        # Save to file.
        with open(self.filename, 'a') as f:
            f.write('\n# %s\n' % datetime.datetime.now())
            for line in string.split('\n'):
                f.write('+%s\n' % line)


