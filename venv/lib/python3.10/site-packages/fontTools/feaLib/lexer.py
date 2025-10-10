from fontTools.feaLib.error import FeatureLibError, IncludedFeaNotFound
from fontTools.feaLib.location import FeatureLibLocation
import re
import os

try:
    import cython
except ImportError:
    # if cython not installed, use mock module with no-op decorators and types
    from fontTools.misc import cython


class Lexer(object):
    NUMBER = "NUMBER"
    HEXADECIMAL = "HEXADECIMAL"
    OCTAL = "OCTAL"
    NUMBERS = (NUMBER, HEXADECIMAL, OCTAL)
    FLOAT = "FLOAT"
    STRING = "STRING"
    NAME = "NAME"
    FILENAME = "FILENAME"
    GLYPHCLASS = "GLYPHCLASS"
    CID = "CID"
    SYMBOL = "SYMBOL"
    COMMENT = "COMMENT"
    NEWLINE = "NEWLINE"
    ANONYMOUS_BLOCK = "ANONYMOUS_BLOCK"

    CHAR_WHITESPACE_ = " \t"
    CHAR_NEWLINE_ = "\r\n"
    CHAR_SYMBOL_ = ",;:-+'{}[]<>()="
    CHAR_DIGIT_ = "0123456789"
    CHAR_HEXDIGIT_ = "0123456789ABCDEFabcdef"
    CHAR_LETTER_ = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
    CHAR_NAME_START_ = CHAR_LETTER_ + "_+*:.^~!\\"
    CHAR_NAME_CONTINUATION_ = CHAR_LETTER_ + CHAR_DIGIT_ + "_.+*:^~!/-"

    RE_GLYPHCLASS = re.compile(r"^[A-Za-z_0-9.\-]+$")

    MODE_NORMAL_ = "NORMAL"
    MODE_FILENAME_ = "FILENAME"

    def __init__(self, text, filename):
        self.filename_ = filename
        self.line_ = 1
        self.pos_ = 0
        self.line_start_ = 0
        self.text_ = text
        self.text_length_ = len(text)
        self.mode_ = Lexer.MODE_NORMAL_

    def __iter__(self):
        return self

    def next(self):  # Python 2
        return self.__next__()

    def __next__(self):  # Python 3
        while True:
            token_type, token, location = self.next_()
            if token_type != Lexer.NEWLINE:
                return (token_type, token, location)

    def location_(self):
        column = self.pos_ - self.line_start_ + 1
        return FeatureLibLocation(self.filename_ or "<features>", self.line_, column)

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
        if cur_char == "#":
            self.scan_until_(Lexer.CHAR_NEWLINE_)
            return (Lexer.COMMENT, text[start : self.pos_], location)

        if self.mode_ is Lexer.MODE_FILENAME_:
            if cur_char != "(":
                raise FeatureLibError("Expected '(' before file name", location)
            self.scan_until_(")")
            cur_char = text[self.pos_] if self.pos_ < limit else None
            if cur_char != ")":
                raise FeatureLibError("Expected ')' after file name", location)
            self.pos_ += 1
            self.mode_ = Lexer.MODE_NORMAL_
            return (Lexer.FILENAME, text[start + 1 : self.pos_ - 1], location)

        if cur_char == "\\" and next_char in Lexer.CHAR_DIGIT_:
            self.pos_ += 1
            self.scan_over_(Lexer.CHAR_DIGIT_)
            return (Lexer.CID, int(text[start + 1 : self.pos_], 10), location)
        if cur_char == "@":
            self.pos_ += 1
            self.scan_over_(Lexer.CHAR_NAME_CONTINUATION_)
            glyphclass = text[start + 1 : self.pos_]
            if len(glyphclass) < 1:
                raise FeatureLibError("Expected glyph class name", location)
            if not Lexer.RE_GLYPHCLASS.match(glyphclass):
                raise FeatureLibError(
                    "Glyph class names must consist of letters, digits, "
                    "underscore, period or hyphen",
                    location,
                )
            return (Lexer.GLYPHCLASS, glyphclass, location)
        if cur_char in Lexer.CHAR_NAME_START_:
            self.pos_ += 1
            self.scan_over_(Lexer.CHAR_NAME_CONTINUATION_)
            token = text[start : self.pos_]
            if token == "include":
                self.mode_ = Lexer.MODE_FILENAME_
            return (Lexer.NAME, token, location)
        if cur_char == "0" and next_char in "xX":
            self.pos_ += 2
            self.scan_over_(Lexer.CHAR_HEXDIGIT_)
            return (Lexer.HEXADECIMAL, int(text[start : self.pos_], 16), location)
        if cur_char == "0" and next_char in Lexer.CHAR_DIGIT_:
            self.scan_over_(Lexer.CHAR_DIGIT_)
            return (Lexer.OCTAL, int(text[start : self.pos_], 8), location)
        if cur_char in Lexer.CHAR_DIGIT_:
            self.scan_over_(Lexer.CHAR_DIGIT_)
            if self.pos_ >= limit or text[self.pos_] != ".":
                return (Lexer.NUMBER, int(text[start : self.pos_], 10), location)
            self.scan_over_(".")
            self.scan_over_(Lexer.CHAR_DIGIT_)
            return (Lexer.FLOAT, float(text[start : self.pos_]), location)
        if cur_char == "-" and next_char in Lexer.CHAR_DIGIT_:
            self.pos_ += 1
            self.scan_over_(Lexer.CHAR_DIGIT_)
            if self.pos_ >= limit or text[self.pos_] != ".":
                return (Lexer.NUMBER, int(text[start : self.pos_], 10), location)
            self.scan_over_(".")
            self.scan_over_(Lexer.CHAR_DIGIT_)
            return (Lexer.FLOAT, float(text[start : self.pos_]), location)
        if cur_char in Lexer.CHAR_SYMBOL_:
            self.pos_ += 1
            return (Lexer.SYMBOL, cur_char, location)
        if cur_char == '"':
            self.pos_ += 1
            self.scan_until_('"')
            if self.pos_ < self.text_length_ and self.text_[self.pos_] == '"':
                self.pos_ += 1
                # strip newlines embedded within a string
                string = re.sub("[\r\n]", "", text[start + 1 : self.pos_ - 1])
                return (Lexer.STRING, string, location)
            else:
                raise FeatureLibError("Expected '\"' to terminate string", location)
        raise FeatureLibError("Unexpected character: %r" % cur_char, location)

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

    def scan_anonymous_block(self, tag):
        location = self.location_()
        tag = tag.strip()
        self.scan_until_(Lexer.CHAR_NEWLINE_)
        self.scan_over_(Lexer.CHAR_NEWLINE_)
        regexp = r"}\s*" + tag + r"\s*;"
        split = re.split(regexp, self.text_[self.pos_ :], maxsplit=1)
        if len(split) != 2:
            raise FeatureLibError(
                "Expected '} %s;' to terminate anonymous block" % tag, location
            )
        self.pos_ += len(split[0])
        return (Lexer.ANONYMOUS_BLOCK, split[0], location)


class IncludingLexer(object):
    """A Lexer that follows include statements.

    The OpenType feature file specification states that due to
    historical reasons, relative imports should be resolved in this
    order:

    1. If the source font is UFO format, then relative to the UFO's
       font directory
    2. relative to the top-level include file
    3. relative to the parent include file

    We only support 1 (via includeDir) and 2.
    """

    def __init__(self, featurefile, *, includeDir=None):
        """Initializes an IncludingLexer.

        Behavior:
            If includeDir is passed, it will be used to determine the top-level
            include directory to use for all encountered include statements. If it is
            not passed, ``os.path.dirname(featurefile)`` will be considered the
            include directory.
        """

        self.lexers_ = [self.make_lexer_(featurefile)]
        self.featurefilepath = self.lexers_[0].filename_
        self.includeDir = includeDir

    def __iter__(self):
        return self

    def next(self):  # Python 2
        return self.__next__()

    def __next__(self):  # Python 3
        while self.lexers_:
            lexer = self.lexers_[-1]
            try:
                token_type, token, location = next(lexer)
            except StopIteration:
                self.lexers_.pop()
                continue
            if token_type is Lexer.NAME and token == "include":
                fname_type, fname_token, fname_location = lexer.next()
                if fname_type is not Lexer.FILENAME:
                    raise FeatureLibError("Expected file name", fname_location)
                # semi_type, semi_token, semi_location = lexer.next()
                # if semi_type is not Lexer.SYMBOL or semi_token != ";":
                #    raise FeatureLibError("Expected ';'", semi_location)
                if os.path.isabs(fname_token):
                    path = fname_token
                else:
                    if self.includeDir is not None:
                        curpath = self.includeDir
                    elif self.featurefilepath is not None:
                        curpath = os.path.dirname(self.featurefilepath)
                    else:
                        # if the IncludingLexer was initialized from an in-memory
                        # file-like stream, it doesn't have a 'name' pointing to
                        # its filesystem path, therefore we fall back to using the
                        # current working directory to resolve relative includes
                        curpath = os.getcwd()
                    path = os.path.join(curpath, fname_token)
                if len(self.lexers_) >= 5:
                    raise FeatureLibError("Too many recursive includes", fname_location)
                try:
                    self.lexers_.append(self.make_lexer_(path))
                except FileNotFoundError as err:
                    raise IncludedFeaNotFound(fname_token, fname_location) from err
            else:
                return (token_type, token, location)
        raise StopIteration()

    @staticmethod
    def make_lexer_(file_or_path):
        if hasattr(file_or_path, "read"):
            fileobj, closing = file_or_path, False
        else:
            filename, closing = file_or_path, True
            fileobj = open(filename, "r", encoding="utf-8-sig")
        data = fileobj.read()
        filename = getattr(fileobj, "name", None)
        if closing:
            fileobj.close()
        return Lexer(data, filename)

    def scan_anonymous_block(self, tag):
        return self.lexers_[-1].scan_anonymous_block(tag)


class NonIncludingLexer(IncludingLexer):
    """Lexer that does not follow `include` statements, emits them as-is."""

    def __next__(self):  # Python 3
        return next(self.lexers_[0])
