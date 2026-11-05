# coding=utf-8

try:
    py2_xrange = xrange  # type: ignore
except NameError:
    py2_xrange = range

try:
    py2_unicode = unicode  # type: ignore
except NameError:
    py2_unicode = str

try:
    py2_long = long  # type: ignore
except NameError:
    py2_long = int
