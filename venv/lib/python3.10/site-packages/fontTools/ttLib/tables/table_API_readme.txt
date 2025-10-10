This folder is a subpackage of ttLib. Each module here is a 
specialized TT/OT table converter: they can convert raw data 
to Python objects and vice versa. Usually you don't need to 
use the modules directly: they are imported and used 
automatically when needed by ttLib.

If you are writing you own table converter the following is 
important.

The modules here have pretty strange names: this is due to the 
fact that we need to map TT table tags (which are case sensitive) 
to filenames (which on Mac and Win aren't case sensitive) as well 
as to Python identifiers. The latter means it can only contain 
[A-Za-z0-9_] and cannot start with a number. 

ttLib provides functions to expand a tag into the format used here:

>>> from fontTools import ttLib
>>> ttLib.tagToIdentifier("FOO ")
'F_O_O_'
>>> ttLib.tagToIdentifier("cvt ")
'_c_v_t'
>>> ttLib.tagToIdentifier("OS/2")
'O_S_2f_2'
>>> ttLib.tagToIdentifier("glyf")
'_g_l_y_f'
>>> 

And vice versa:

>>> ttLib.identifierToTag("F_O_O_")
'FOO '
>>> ttLib.identifierToTag("_c_v_t")
'cvt '
>>> ttLib.identifierToTag("O_S_2f_2")
'OS/2'
>>> ttLib.identifierToTag("_g_l_y_f")
'glyf'
>>> 

Eg. the 'glyf' table converter lives in a Python file called:

	_g_l_y_f.py

The converter itself is a class, named "table_" + expandedtag. Eg:

	class table__g_l_y_f:
		etc.

Note that if you _do_ need to use such modules or classes manually, 
there are two convenient API functions that let you find them by tag:

>>> ttLib.getTableModule('glyf')
<module 'ttLib.tables._g_l_y_f'>
>>> ttLib.getTableClass('glyf')
<class ttLib.tables._g_l_y_f.table__g_l_y_f at 645f400>
>>> 

You must subclass from DefaultTable.DefaultTable. It provides some default
behavior, as well as a constructor method (__init__) that you don't need to 
override.

Your converter should minimally provide two methods:

class table_F_O_O_(DefaultTable.DefaultTable): # converter for table 'FOO '
	
	def decompile(self, data, ttFont):
		# 'data' is the raw table data. Unpack it into a
		# Python data structure.
		# 'ttFont' is a ttLib.TTfile instance, enabling you to
		# refer to other tables. Do ***not*** keep a reference to
		# it: it will cause a circular reference (ttFont saves 
		# a reference to us), and that means we'll be leaking 
		# memory. If you need to use it in other methods, just 
		# pass it around as a method argument.
	
	def compile(self, ttFont):
		# Return the raw data, as converted from the Python
		# data structure. 
		# Again, 'ttFont' is there so you can access other tables.
		# Same warning applies.

If you want to support TTX import/export as well, you need to provide two
additional methods:

	def toXML(self, writer, ttFont):
		# XXX
	
	def fromXML(self, (name, attrs, content), ttFont):
		# XXX

