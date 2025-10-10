#------------------------------------------------------------------------------
# pycparser: c_lexer.py
#
# CLexer class: lexer for the C language
#
# Eli Bendersky [https://eli.thegreenplace.net/]
# License: BSD
#------------------------------------------------------------------------------
import re

from .ply import lex
from .ply.lex import TOKEN


class CLexer(object):
    """ A lexer for the C language. After building it, set the
        input text with input(), and call token() to get new
        tokens.

        The public attribute filename can be set to an initial
        filename, but the lexer will update it upon #line
        directives.
    """
    def __init__(self, error_func, on_lbrace_func, on_rbrace_func,
                 type_lookup_func):
        """ Create a new Lexer.

            error_func:
                An error function. Will be called with an error
                message, line and column as arguments, in case of
                an error during lexing.

            on_lbrace_func, on_rbrace_func:
                Called when an LBRACE or RBRACE is encountered
                (likely to push/pop type_lookup_func's scope)

            type_lookup_func:
                A type lookup function. Given a string, it must
                return True IFF this string is a name of a type
                that was defined with a typedef earlier.
        """
        self.error_func = error_func
        self.on_lbrace_func = on_lbrace_func
        self.on_rbrace_func = on_rbrace_func
        self.type_lookup_func = type_lookup_func
        self.filename = ''

        # Keeps track of the last token returned from self.token()
        self.last_token = None

        # Allow either "# line" or "# <num>" to support GCC's
        # cpp output
        #
        self.line_pattern = re.compile(r'([ \t]*line\W)|([ \t]*\d+)')
        self.pragma_pattern = re.compile(r'[ \t]*pragma\W')

    def build(self, **kwargs):
        """ Builds the lexer from the specification. Must be
            called after the lexer object is created.

            This method exists separately, because the PLY
            manual warns against calling lex.lex inside
            __init__
        """
        self.lexer = lex.lex(object=self, **kwargs)

    def reset_lineno(self):
        """ Resets the internal line number counter of the lexer.
        """
        self.lexer.lineno = 1

    def input(self, text):
        self.lexer.input(text)

    def token(self):
        self.last_token = self.lexer.token()
        return self.last_token

    def find_tok_column(self, token):
        """ Find the column of the token in its line.
        """
        last_cr = self.lexer.lexdata.rfind('\n', 0, token.lexpos)
        return token.lexpos - last_cr

    ######################--   PRIVATE   --######################

    ##
    ## Internal auxiliary methods
    ##
    def _error(self, msg, token):
        location = self._make_tok_location(token)
        self.error_func(msg, location[0], location[1])
        self.lexer.skip(1)

    def _make_tok_location(self, token):
        return (token.lineno, self.find_tok_column(token))

    ##
    ## Reserved keywords
    ##
    keywords = (
        'AUTO', 'BREAK', 'CASE', 'CHAR', 'CONST',
        'CONTINUE', 'DEFAULT', 'DO', 'DOUBLE', 'ELSE', 'ENUM', 'EXTERN',
        'FLOAT', 'FOR', 'GOTO', 'IF', 'INLINE', 'INT', 'LONG',
        'REGISTER', 'OFFSETOF',
        'RESTRICT', 'RETURN', 'SHORT', 'SIGNED', 'SIZEOF', 'STATIC', 'STRUCT',
        'SWITCH', 'TYPEDEF', 'UNION', 'UNSIGNED', 'VOID',
        'VOLATILE', 'WHILE', '__INT128',
    )

    keywords_new = (
        '_BOOL', '_COMPLEX',
        '_NORETURN', '_THREAD_LOCAL', '_STATIC_ASSERT',
        '_ATOMIC', '_ALIGNOF', '_ALIGNAS',
        '_PRAGMA',
        )

    keyword_map = {}

    for keyword in keywords:
        keyword_map[keyword.lower()] = keyword

    for keyword in keywords_new:
        keyword_map[keyword[:2].upper() + keyword[2:].lower()] = keyword

    ##
    ## All the tokens recognized by the lexer
    ##
    tokens = keywords + keywords_new + (
        # Identifiers
        'ID',

        # Type identifiers (identifiers previously defined as
        # types with typedef)
        'TYPEID',

        # constants
        'INT_CONST_DEC', 'INT_CONST_OCT', 'INT_CONST_HEX', 'INT_CONST_BIN', 'INT_CONST_CHAR',
        'FLOAT_CONST', 'HEX_FLOAT_CONST',
        'CHAR_CONST',
        'WCHAR_CONST',
        'U8CHAR_CONST',
        'U16CHAR_CONST',
        'U32CHAR_CONST',

        # String literals
        'STRING_LITERAL',
        'WSTRING_LITERAL',
        'U8STRING_LITERAL',
        'U16STRING_LITERAL',
        'U32STRING_LITERAL',

        # Operators
        'PLUS', 'MINUS', 'TIMES', 'DIVIDE', 'MOD',
        'OR', 'AND', 'NOT', 'XOR', 'LSHIFT', 'RSHIFT',
        'LOR', 'LAND', 'LNOT',
        'LT', 'LE', 'GT', 'GE', 'EQ', 'NE',

        # Assignment
        'EQUALS', 'TIMESEQUAL', 'DIVEQUAL', 'MODEQUAL',
        'PLUSEQUAL', 'MINUSEQUAL',
        'LSHIFTEQUAL','RSHIFTEQUAL', 'ANDEQUAL', 'XOREQUAL',
        'OREQUAL',

        # Increment/decrement
        'PLUSPLUS', 'MINUSMINUS',

        # Structure dereference (->)
        'ARROW',

        # Conditional operator (?)
        'CONDOP',

        # Delimiters
        'LPAREN', 'RPAREN',         # ( )
        'LBRACKET', 'RBRACKET',     # [ ]
        'LBRACE', 'RBRACE',         # { }
        'COMMA', 'PERIOD',          # . ,
        'SEMI', 'COLON',            # ; :

        # Ellipsis (...)
        'ELLIPSIS',

        # pre-processor
        'PPHASH',       # '#'
        'PPPRAGMA',     # 'pragma'
        'PPPRAGMASTR',
    )

    ##
    ## Regexes for use in tokens
    ##
    ##

    # valid C identifiers (K&R2: A.2.3), plus '$' (supported by some compilers)
    identifier = r'[a-zA-Z_$][0-9a-zA-Z_$]*'

    hex_prefix = '0[xX]'
    hex_digits = '[0-9a-fA-F]+'
    bin_prefix = '0[bB]'
    bin_digits = '[01]+'

    # integer constants (K&R2: A.2.5.1)
    integer_suffix_opt = r'(([uU]ll)|([uU]LL)|(ll[uU]?)|(LL[uU]?)|([uU][lL])|([lL][uU]?)|[uU])?'
    decimal_constant = '(0'+integer_suffix_opt+')|([1-9][0-9]*'+integer_suffix_opt+')'
    octal_constant = '0[0-7]*'+integer_suffix_opt
    hex_constant = hex_prefix+hex_digits+integer_suffix_opt
    bin_constant = bin_prefix+bin_digits+integer_suffix_opt

    bad_octal_constant = '0[0-7]*[89]'

    # comments are not supported
    unsupported_c_style_comment = r'\/\*'
    unsupported_cxx_style_comment = r'\/\/'

    # character constants (K&R2: A.2.5.2)
    # Note: a-zA-Z and '.-~^_!=&;,' are allowed as escape chars to support #line
    # directives with Windows paths as filenames (..\..\dir\file)
    # For the same reason, decimal_escape allows all digit sequences. We want to
    # parse all correct code, even if it means to sometimes parse incorrect
    # code.
    #
    # The original regexes were taken verbatim from the C syntax definition,
    # and were later modified to avoid worst-case exponential running time.
    #
    #   simple_escape = r"""([a-zA-Z._~!=&\^\-\\?'"])"""
    #   decimal_escape = r"""(\d+)"""
    #   hex_escape = r"""(x[0-9a-fA-F]+)"""
    #   bad_escape = r"""([\\][^a-zA-Z._~^!=&\^\-\\?'"x0-7])"""
    #
    # The following modifications were made to avoid the ambiguity that allowed backtracking:
    # (https://github.com/eliben/pycparser/issues/61)
    #
    # - \x was removed from simple_escape, unless it was not followed by a hex digit, to avoid ambiguity with hex_escape.
    # - hex_escape allows one or more hex characters, but requires that the next character(if any) is not hex
    # - decimal_escape allows one or more decimal characters, but requires that the next character(if any) is not a decimal
    # - bad_escape does not allow any decimals (8-9), to avoid conflicting with the permissive decimal_escape.
    #
    # Without this change, python's `re` module would recursively try parsing each ambiguous escape sequence in multiple ways.
    # e.g. `\123` could be parsed as `\1`+`23`, `\12`+`3`, and `\123`.

    simple_escape = r"""([a-wyzA-Z._~!=&\^\-\\?'"]|x(?![0-9a-fA-F]))"""
    decimal_escape = r"""(\d+)(?!\d)"""
    hex_escape = r"""(x[0-9a-fA-F]+)(?![0-9a-fA-F])"""
    bad_escape = r"""([\\][^a-zA-Z._~^!=&\^\-\\?'"x0-9])"""

    escape_sequence = r"""(\\("""+simple_escape+'|'+decimal_escape+'|'+hex_escape+'))'

    # This complicated regex with lookahead might be slow for strings, so because all of the valid escapes (including \x) allowed
    # 0 or more non-escaped characters after the first character, simple_escape+decimal_escape+hex_escape got simplified to

    escape_sequence_start_in_string = r"""(\\[0-9a-zA-Z._~!=&\^\-\\?'"])"""

    cconst_char = r"""([^'\\\n]|"""+escape_sequence+')'
    char_const = "'"+cconst_char+"'"
    wchar_const = 'L'+char_const
    u8char_const = 'u8'+char_const
    u16char_const = 'u'+char_const
    u32char_const = 'U'+char_const
    multicharacter_constant = "'"+cconst_char+"{2,4}'"
    unmatched_quote = "('"+cconst_char+"*\\n)|('"+cconst_char+"*$)"
    bad_char_const = r"""('"""+cconst_char+"""[^'\n]+')|('')|('"""+bad_escape+r"""[^'\n]*')"""

    # string literals (K&R2: A.2.6)
    string_char = r"""([^"\\\n]|"""+escape_sequence_start_in_string+')'
    string_literal = '"'+string_char+'*"'
    wstring_literal = 'L'+string_literal
    u8string_literal = 'u8'+string_literal
    u16string_literal = 'u'+string_literal
    u32string_literal = 'U'+string_literal
    bad_string_literal = '"'+string_char+'*'+bad_escape+string_char+'*"'

    # floating constants (K&R2: A.2.5.3)
    exponent_part = r"""([eE][-+]?[0-9]+)"""
    fractional_constant = r"""([0-9]*\.[0-9]+)|([0-9]+\.)"""
    floating_constant = '(((('+fractional_constant+')'+exponent_part+'?)|([0-9]+'+exponent_part+'))[FfLl]?)'
    binary_exponent_part = r'''([pP][+-]?[0-9]+)'''
    hex_fractional_constant = '((('+hex_digits+r""")?\."""+hex_digits+')|('+hex_digits+r"""\.))"""
    hex_floating_constant = '('+hex_prefix+'('+hex_digits+'|'+hex_fractional_constant+')'+binary_exponent_part+'[FfLl]?)'

    ##
    ## Lexer states: used for preprocessor \n-terminated directives
    ##
    states = (
        # ppline: preprocessor line directives
        #
        ('ppline', 'exclusive'),

        # pppragma: pragma
        #
        ('pppragma', 'exclusive'),
    )

    def t_PPHASH(self, t):
        r'[ \t]*\#'
        if self.line_pattern.match(t.lexer.lexdata, pos=t.lexer.lexpos):
            t.lexer.begin('ppline')
            self.pp_line = self.pp_filename = None
        elif self.pragma_pattern.match(t.lexer.lexdata, pos=t.lexer.lexpos):
            t.lexer.begin('pppragma')
        else:
            t.type = 'PPHASH'
            return t

    ##
    ## Rules for the ppline state
    ##
    @TOKEN(string_literal)
    def t_ppline_FILENAME(self, t):
        if self.pp_line is None:
            self._error('filename before line number in #line', t)
        else:
            self.pp_filename = t.value.lstrip('"').rstrip('"')

    @TOKEN(decimal_constant)
    def t_ppline_LINE_NUMBER(self, t):
        if self.pp_line is None:
            self.pp_line = t.value
        else:
            # Ignore: GCC's cpp sometimes inserts a numeric flag
            # after the file name
            pass

    def t_ppline_NEWLINE(self, t):
        r'\n'
        if self.pp_line is None:
            self._error('line number missing in #line', t)
        else:
            self.lexer.lineno = int(self.pp_line)

            if self.pp_filename is not None:
                self.filename = self.pp_filename

        t.lexer.begin('INITIAL')

    def t_ppline_PPLINE(self, t):
        r'line'
        pass

    t_ppline_ignore = ' \t'

    def t_ppline_error(self, t):
        self._error('invalid #line directive', t)

    ##
    ## Rules for the pppragma state
    ##
    def t_pppragma_NEWLINE(self, t):
        r'\n'
        t.lexer.lineno += 1
        t.lexer.begin('INITIAL')

    def t_pppragma_PPPRAGMA(self, t):
        r'pragma'
        return t

    t_pppragma_ignore = ' \t'

    def t_pppragma_STR(self, t):
        '.+'
        t.type = 'PPPRAGMASTR'
        return t

    def t_pppragma_error(self, t):
        self._error('invalid #pragma directive', t)

    ##
    ## Rules for the normal state
    ##
    t_ignore = ' \t'

    # Newlines
    def t_NEWLINE(self, t):
        r'\n+'
        t.lexer.lineno += t.value.count("\n")

    # Operators
    t_PLUS              = r'\+'
    t_MINUS             = r'-'
    t_TIMES             = r'\*'
    t_DIVIDE            = r'/'
    t_MOD               = r'%'
    t_OR                = r'\|'
    t_AND               = r'&'
    t_NOT               = r'~'
    t_XOR               = r'\^'
    t_LSHIFT            = r'<<'
    t_RSHIFT            = r'>>'
    t_LOR               = r'\|\|'
    t_LAND              = r'&&'
    t_LNOT              = r'!'
    t_LT                = r'<'
    t_GT                = r'>'
    t_LE                = r'<='
    t_GE                = r'>='
    t_EQ                = r'=='
    t_NE                = r'!='

    # Assignment operators
    t_EQUALS            = r'='
    t_TIMESEQUAL        = r'\*='
    t_DIVEQUAL          = r'/='
    t_MODEQUAL          = r'%='
    t_PLUSEQUAL         = r'\+='
    t_MINUSEQUAL        = r'-='
    t_LSHIFTEQUAL       = r'<<='
    t_RSHIFTEQUAL       = r'>>='
    t_ANDEQUAL          = r'&='
    t_OREQUAL           = r'\|='
    t_XOREQUAL          = r'\^='

    # Increment/decrement
    t_PLUSPLUS          = r'\+\+'
    t_MINUSMINUS        = r'--'

    # ->
    t_ARROW             = r'->'

    # ?
    t_CONDOP            = r'\?'

    # Delimiters
    t_LPAREN            = r'\('
    t_RPAREN            = r'\)'
    t_LBRACKET          = r'\['
    t_RBRACKET          = r'\]'
    t_COMMA             = r','
    t_PERIOD            = r'\.'
    t_SEMI              = r';'
    t_COLON             = r':'
    t_ELLIPSIS          = r'\.\.\.'

    # Scope delimiters
    # To see why on_lbrace_func is needed, consider:
    #   typedef char TT;
    #   void foo(int TT) { TT = 10; }
    #   TT x = 5;
    # Outside the function, TT is a typedef, but inside (starting and ending
    # with the braces) it's a parameter.  The trouble begins with yacc's
    # lookahead token.  If we open a new scope in brace_open, then TT has
    # already been read and incorrectly interpreted as TYPEID.  So, we need
    # to open and close scopes from within the lexer.
    # Similar for the TT immediately outside the end of the function.
    #
    @TOKEN(r'\{')
    def t_LBRACE(self, t):
        self.on_lbrace_func()
        return t
    @TOKEN(r'\}')
    def t_RBRACE(self, t):
        self.on_rbrace_func()
        return t

    t_STRING_LITERAL = string_literal

    # The following floating and integer constants are defined as
    # functions to impose a strict order (otherwise, decimal
    # is placed before the others because its regex is longer,
    # and this is bad)
    #
    @TOKEN(floating_constant)
    def t_FLOAT_CONST(self, t):
        return t

    @TOKEN(hex_floating_constant)
    def t_HEX_FLOAT_CONST(self, t):
        return t

    @TOKEN(hex_constant)
    def t_INT_CONST_HEX(self, t):
        return t

    @TOKEN(bin_constant)
    def t_INT_CONST_BIN(self, t):
        return t

    @TOKEN(bad_octal_constant)
    def t_BAD_CONST_OCT(self, t):
        msg = "Invalid octal constant"
        self._error(msg, t)

    @TOKEN(unsupported_c_style_comment)
    def t_UNSUPPORTED_C_STYLE_COMMENT(self, t):
        msg = "Comments are not supported, see https://github.com/eliben/pycparser#3using."
        self._error(msg, t)

    @TOKEN(unsupported_cxx_style_comment)
    def t_UNSUPPORTED_CXX_STYLE_COMMENT(self, t):
        msg = "Comments are not supported, see https://github.com/eliben/pycparser#3using."
        self._error(msg, t)

    @TOKEN(octal_constant)
    def t_INT_CONST_OCT(self, t):
        return t

    @TOKEN(decimal_constant)
    def t_INT_CONST_DEC(self, t):
        return t

    # Must come before bad_char_const, to prevent it from
    # catching valid char constants as invalid
    #
    @TOKEN(multicharacter_constant)
    def t_INT_CONST_CHAR(self, t):
        return t

    @TOKEN(char_const)
    def t_CHAR_CONST(self, t):
        return t

    @TOKEN(wchar_const)
    def t_WCHAR_CONST(self, t):
        return t

    @TOKEN(u8char_const)
    def t_U8CHAR_CONST(self, t):
        return t

    @TOKEN(u16char_const)
    def t_U16CHAR_CONST(self, t):
        return t

    @TOKEN(u32char_const)
    def t_U32CHAR_CONST(self, t):
        return t

    @TOKEN(unmatched_quote)
    def t_UNMATCHED_QUOTE(self, t):
        msg = "Unmatched '"
        self._error(msg, t)

    @TOKEN(bad_char_const)
    def t_BAD_CHAR_CONST(self, t):
        msg = "Invalid char constant %s" % t.value
        self._error(msg, t)

    @TOKEN(wstring_literal)
    def t_WSTRING_LITERAL(self, t):
        return t

    @TOKEN(u8string_literal)
    def t_U8STRING_LITERAL(self, t):
        return t

    @TOKEN(u16string_literal)
    def t_U16STRING_LITERAL(self, t):
        return t

    @TOKEN(u32string_literal)
    def t_U32STRING_LITERAL(self, t):
        return t

    # unmatched string literals are caught by the preprocessor

    @TOKEN(bad_string_literal)
    def t_BAD_STRING_LITERAL(self, t):
        msg = "String contains invalid escape code"
        self._error(msg, t)

    @TOKEN(identifier)
    def t_ID(self, t):
        t.type = self.keyword_map.get(t.value, "ID")
        if t.type == 'ID' and self.type_lookup_func(t.value):
            t.type = "TYPEID"
        return t

    def t_error(self, t):
        msg = 'Illegal character %s' % repr(t.value[0])
        self._error(msg, t)
