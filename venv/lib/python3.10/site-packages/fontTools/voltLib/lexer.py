from fontTools.voltLib.error import VoltLibError


class Lexer(object):
    NUMBER = "NUMBER"
    STRING = "STRING"
    NAME = "NAME"
    NEWLINE = "NEWLINE"

    CHAR_WHITESPACE_ = " \t"
    CHAR_NEWLINE_ = "\r\n"
    CHAR_DIGIT_ = "0123456789"
    CHAR_UC_LETTER_ = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    CHAR_LC_LETTER_ = "abcdefghijklmnopqrstuvwxyz"
    CHAR_UNDERSCORE_ = "_"
    CHAR_PERIOD_ = "."
    CHAR_NAME_START_ = (
        CHAR_UC_LETTER_ + CHAR_LC_LETTER_ + CHAR_PERIOD_ + CHAR_UNDERSCORE_
    )
    CHAR_NAME_CONTINUATION_ = CHAR_NAME_START_ + CHAR_DIGIT_

    def __init__(self, text, filename):
        self.filename_ = filename
        self.line_ = 1
        self.pos_ = 0
        self.line_start_ = 0
        self.text_ = text
        self.text_length_ = len(text)

    def __iter__(self):
        return self

    def next(self):  # Python 2
        return self.__next__()

    def __next__(self):  # Python 3
        while True:
            token_type, token, location = self.next_()
            if token_type not in {Lexer.NEWLINE}:
                return (token_type, token, location)

    def location_(self):
        column = self.pos_ - self.line_start_ + 1
        return (self.filename_ or "<volt>", self.line_, column)

    def next_(self):
        self.scan_over_(Lexer.CHAR_WHITESPACE_)
        location = self.location_()
        start = self.pos_
        text = self.text_
        limit = len(text)
        if start >= limit:
            raise StopIteration()
        cur_char = text[start]
        next_char = text[start + 1] if start + 1 < limit else None

        if cur_char == "\n":
            self.pos_ += 1
            self.line_ += 1
            self.line_start_ = self.pos_
            return (Lexer.NEWLINE, None, location)
        if cur_char == "\r":
            self.pos_ += 2 if next_char == "\n" else 1
            self.line_ += 1
            self.line_start_ = self.pos_
            return (Lexer.NEWLINE, None, location)
        if cur_char == '"':
            self.pos_ += 1
            self.scan_until_('"\r\n')
            if self.pos_ < self.text_length_ and self.text_[self.pos_] == '"':
                self.pos_ += 1
                return (Lexer.STRING, text[start + 1 : self.pos_ - 1], location)
            else:
                raise VoltLibError("Expected '\"' to terminate string", location)
        if cur_char in Lexer.CHAR_NAME_START_:
            self.pos_ += 1
            self.scan_over_(Lexer.CHAR_NAME_CONTINUATION_)
            token = text[start : self.pos_]
            return (Lexer.NAME, token, location)
        if cur_char in Lexer.CHAR_DIGIT_:
            self.scan_over_(Lexer.CHAR_DIGIT_)
            return (Lexer.NUMBER, int(text[start : self.pos_], 10), location)
        if cur_char == "-" and next_char in Lexer.CHAR_DIGIT_:
            self.pos_ += 1
            self.scan_over_(Lexer.CHAR_DIGIT_)
            return (Lexer.NUMBER, int(text[start : self.pos_], 10), location)
        raise VoltLibError("Unexpected character: '%s'" % cur_char, location)

    def scan_over_(self, valid):
        p = self.pos_
        while p < self.text_length_ and self.text_[p] in valid:
            p += 1
        self.pos_ = p

    def scan_until_(self, stop_at):
        p = self.pos_
        while p < self.text_length_ and self.text_[p] not in stop_at:
            p += 1
        self.pos_ = p
