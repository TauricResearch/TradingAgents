#-----------------------------------------------------------------
# pycparser: _build_tables.py
#
# A dummy for generating the lexing/parsing tables and and
# compiling them into .pyc for faster execution in optimized mode.
# Also generates AST code from the configuration file.
# Should be called from the pycparser directory.
#
# Eli Bendersky [https://eli.thegreenplace.net/]
# License: BSD
#-----------------------------------------------------------------

# Insert '.' and '..' as first entries to the search path for modules.
# Restricted environments like embeddable python do not include the
# current working directory on startup.
import importlib
import sys
sys.path[0:0] = ['.', '..']

# Generate c_ast.py
from _ast_gen import ASTCodeGenerator
ast_gen = ASTCodeGenerator('_c_ast.cfg')
ast_gen.generate(open('c_ast.py', 'w'))

from pycparser import c_parser

# Generates the tables
#
c_parser.CParser(
    lex_optimize=True,
    yacc_debug=False,
    yacc_optimize=True)

# Load to compile into .pyc
#
importlib.invalidate_caches()

import lextab
import yacctab
import c_ast
