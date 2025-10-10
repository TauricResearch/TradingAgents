"""
formlayout
==========

Module creating Qt form dialogs/layouts to edit various type of parameters


formlayout License Agreement (MIT License)
------------------------------------------

Copyright (c) 2009 Pierre Raybaut

Permission is hereby granted, free of charge, to any person
obtaining a copy of this software and associated documentation
files (the "Software"), to deal in the Software without
restriction, including without limitation the rights to use,
copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the
Software is furnished to do so, subject to the following
conditions:

The above copyright notice and this permission notice shall be
included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES
OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT
HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY,
WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR
OTHER DEALINGS IN THE SOFTWARE.
"""

# History:
# 1.0.10: added float validator
#         (disable "Ok" and "Apply" button when not valid)
# 1.0.7: added support for "Apply" button
# 1.0.6: code cleaning

__version__ = '1.0.10'
__license__ = __doc__

from ast import literal_eval

import copy
import datetime
import logging
from numbers import Integral, Real

from matplotlib import _api, colors as mcolors
from matplotlib.backends.qt_compat import _to_int, QtGui, QtWidgets, QtCore

_log = logging.getLogger(__name__)

BLACKLIST = {"title", "label"}


class ColorButton(QtWidgets.QPushButton):
    """
    Color choosing push button
    """
    colorChanged = QtCore.Signal(QtGui.QColor)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(20, 20)
        self.setIconSize(QtCore.QSize(12, 12))
        self.clicked.connect(self.choose_color)
        self._color = QtGui.QColor()

    def choose_color(self):
        color = QtWidgets.QColorDialog.getColor(
            self._color, self.parentWidget(), "",
            QtWidgets.QColorDialog.ColorDialogOption.ShowAlphaChannel)
        if color.isValid():
            self.set_color(color)

    def get_color(self):
        return self._color

    @QtCore.Slot(QtGui.QColor)
    def set_color(self, color):
        if color != self._color:
            self._color = color
            self.colorChanged.emit(self._color)
            pixmap = QtGui.QPixmap(self.iconSize())
            pixmap.fill(color)
            self.setIcon(QtGui.QIcon(pixmap))

    color = QtCore.Property(QtGui.QColor, get_color, set_color)


def to_qcolor(color):
    """Create a QColor from a matplotlib color"""
    qcolor = QtGui.QColor()
    try:
        rgba = mcolors.to_rgba(color)
    except ValueError:
        _api.warn_external(f'Ignoring invalid color {color!r}')
        return qcolor  # return invalid QColor
    qcolor.setRgbF(*rgba)
    return qcolor


class ColorLayout(QtWidgets.QHBoxLayout):
    """Color-specialized QLineEdit layout"""
    def __init__(self, color, parent=None):
        super().__init__()
        assert isinstance(color, QtGui.QColor)
        self.lineedit = QtWidgets.QLineEdit(
            mcolors.to_hex(color.getRgbF(), keep_alpha=True), parent)
        self.lineedit.editingFinished.connect(self.update_color)
        self.addWidget(self.lineedit)
        self.colorbtn = ColorButton(parent)
        self.colorbtn.color = color
        self.colorbtn.colorChanged.connect(self.update_text)
        self.addWidget(self.colorbtn)

    def update_color(self):
        color = self.text()
        qcolor = to_qcolor(color)  # defaults to black if not qcolor.isValid()
        self.colorbtn.color = qcolor

    def update_text(self, color):
        self.lineedit.setText(mcolors.to_hex(color.getRgbF(), keep_alpha=True))

    def text(self):
        return self.lineedit.text()


def font_is_installed(font):
    """Check if font is installed"""
    return [fam for fam in QtGui.QFontDatabase().families()
            if str(fam) == font]


def tuple_to_qfont(tup):
    """
    Create a QFont from tuple:
        (family [string], size [int], italic [bool], bold [bool])
    """
    if not (isinstance(tup, tuple) and len(tup) == 4
            and font_is_installed(tup[0])
            and isinstance(tup[1], Integral)
            and isinstance(tup[2], bool)
            and isinstance(tup[3], bool)):
        return None
    font = QtGui.QFont()
    family, size, italic, bold = tup
    font.setFamily(family)
    font.setPointSize(size)
    font.setItalic(italic)
    font.setBold(bold)
    return font


def qfont_to_tuple(font):
    return (str(font.family()), int(font.pointSize()),
            font.italic(), font.bold())


class FontLayout(QtWidgets.QGridLayout):
    """Font selection"""
    def __init__(self, value, parent=None):
        super().__init__()
        font = tuple_to_qfont(value)
        assert font is not None

        # Font family
        self.family = QtWidgets.QFontComboBox(parent)
        self.family.setCurrentFont(font)
        self.addWidget(self.family, 0, 0, 1, -1)

        # Font size
        self.size = QtWidgets.QComboBox(parent)
        self.size.setEditable(True)
        sizelist = [*range(6, 12), *range(12, 30, 2), 36, 48, 72]
        size = font.pointSize()
        if size not in sizelist:
            sizelist.append(size)
            sizelist.sort()
        self.size.addItems([str(s) for s in sizelist])
        self.size.setCurrentIndex(sizelist.index(size))
        self.addWidget(self.size, 1, 0)

        # Italic or not
        self.italic = QtWidgets.QCheckBox(self.tr("Italic"), parent)
        self.italic.setChecked(font.italic())
        self.addWidget(self.italic, 1, 1)

        # Bold or not
        self.bold = QtWidgets.QCheckBox(self.tr("Bold"), parent)
        self.bold.setChecked(font.bold())
        self.addWidget(self.bold, 1, 2)

    def get_font(self):
        font = self.family.currentFont()
        font.setItalic(self.italic.isChecked())
        font.setBold(self.bold.isChecked())
        font.setPointSize(int(self.size.currentText()))
        return qfont_to_tuple(font)


def is_edit_valid(edit):
    text = edit.text()
    state = edit.validator().validate(text, 0)[0]
    return state == QtGui.QDoubleValidator.State.Acceptable


class FormWidget(QtWidgets.QWidget):
    update_buttons = QtCore.Signal()

    def __init__(self, data, comment="", with_margin=False, parent=None):
        """
        Parameters
        ----------
        data : list of (label, value) pairs
            The data to be edited in the form.
        comment : str, optional
        with_margin : bool, default: False
            If False, the form elements reach to the border of the widget.
            This is the desired behavior if the FormWidget is used as a widget
            alongside with other widgets such as a QComboBox, which also do
            not have a margin around them.
            However, a margin can be desired if the FormWidget is the only
            widget within a container, e.g. a tab in a QTabWidget.
        parent : QWidget or None
            The parent widget.
        """
        super().__init__(parent)
        self.data = copy.deepcopy(data)
        self.widgets = []
        self.formlayout = QtWidgets.QFormLayout(self)
        if not with_margin:
            self.formlayout.setContentsMargins(0, 0, 0, 0)
        if comment:
            self.formlayout.addRow(QtWidgets.QLabel(comment))
            self.formlayout.addRow(QtWidgets.QLabel(" "))

    def get_dialog(self):
        """Return FormDialog instance"""
        dialog = self.parent()
        while not isinstance(dialog, QtWidgets.QDialog):
            dialog = dialog.parent()
        return dialog

    def setup(self):
        for label, value in self.data:
            if label is None and value is None:
                # Separator: (None, None)
                self.formlayout.addRow(QtWidgets.QLabel(" "),
                                       QtWidgets.QLabel(" "))
                self.widgets.append(None)
                continue
            elif label is None:
                # Comment
                self.formlayout.addRow(QtWidgets.QLabel(value))
                self.widgets.append(None)
                continue
            elif tuple_to_qfont(value) is not None:
                field = FontLayout(value, self)
            elif (label.lower() not in BLACKLIST
                  and mcolors.is_color_like(value)):
                field = ColorLayout(to_qcolor(value), self)
            elif isinstance(value, str):
                field = QtWidgets.QLineEdit(value, self)
            elif isinstance(value, (list, tuple)):
                if isinstance(value, tuple):
                    value = list(value)
                # Note: get() below checks the type of value[0] in self.data so
                # it is essential that value gets modified in-place.
                # This means that the code is actually broken in the case where
                # value is a tuple, but fortunately we always pass a list...
                selindex = value.pop(0)
                field = QtWidgets.QComboBox(self)
                if isinstance(value[0], (list, tuple)):
                    keys = [key for key, _val in value]
                    value = [val for _key, val in value]
                else:
                    keys = value
                field.addItems(value)
                if selindex in value:
                    selindex = value.index(selindex)
                elif selindex in keys:
                    selindex = keys.index(selindex)
                elif not isinstance(selindex, Integral):
                    _log.warning(
                        "index '%s' is invalid (label: %s, value: %s)",
                        selindex, label, value)
                    selindex = 0
                field.setCurrentIndex(selindex)
            elif isinstance(value, bool):
                field = QtWidgets.QCheckBox(self)
                field.setChecked(value)
            elif isinstance(value, Integral):
                field = QtWidgets.QSpinBox(self)
                field.setRange(-10**9, 10**9)
                field.setValue(value)
            elif isinstance(value, Real):
                field = QtWidgets.QLineEdit(repr(value), self)
                field.setCursorPosition(0)
                field.setValidator(QtGui.QDoubleValidator(field))
                field.validator().setLocale(QtCore.QLocale("C"))
                dialog = self.get_dialog()
                dialog.register_float_field(field)
                field.textChanged.connect(lambda text: dialog.update_buttons())
            elif isinstance(value, datetime.datetime):
                field = QtWidgets.QDateTimeEdit(self)
                field.setDateTime(value)
            elif isinstance(value, datetime.date):
                field = QtWidgets.QDateEdit(self)
                field.setDate(value)
            else:
                field = QtWidgets.QLineEdit(repr(value), self)
            self.formlayout.addRow(label, field)
            self.widgets.append(field)

    def get(self):
        valuelist = []
        for index, (label, value) in enumerate(self.data):
            field = self.widgets[index]
            if label is None:
                # Separator / Comment
                continue
            elif tuple_to_qfont(value) is not None:
                value = field.get_font()
            elif isinstance(value, str) or mcolors.is_color_like(value):
                value = str(field.text())
            elif isinstance(value, (list, tuple)):
                index = int(field.currentIndex())
                if isinstance(value[0], (list, tuple)):
                    value = value[index][0]
                else:
                    value = value[index]
            elif isinstance(value, bool):
                value = field.isChecked()
            elif isinstance(value, Integral):
                value = int(field.value())
            elif isinstance(value, Real):
                value = float(str(field.text()))
            elif isinstance(value, datetime.datetime):
                datetime_ = field.dateTime()
                if hasattr(datetime_, "toPyDateTime"):
                    value = datetime_.toPyDateTime()
                else:
                    value = datetime_.toPython()
            elif isinstance(value, datetime.date):
                date_ = field.date()
                if hasattr(date_, "toPyDate"):
                    value = date_.toPyDate()
                else:
                    value = date_.toPython()
            else:
                value = literal_eval(str(field.text()))
            valuelist.append(value)
        return valuelist


class FormComboWidget(QtWidgets.QWidget):
    update_buttons = QtCore.Signal()

    def __init__(self, datalist, comment="", parent=None):
        super().__init__(parent)
        layout = QtWidgets.QVBoxLayout()
        self.setLayout(layout)
        self.combobox = QtWidgets.QComboBox()
        layout.addWidget(self.combobox)

        self.stackwidget = QtWidgets.QStackedWidget(self)
        layout.addWidget(self.stackwidget)
        self.combobox.currentIndexChanged.connect(
            self.stackwidget.setCurrentIndex)

        self.widgetlist = []
        for data, title, comment in datalist:
            self.combobox.addItem(title)
            widget = FormWidget(data, comment=comment, parent=self)
            self.stackwidget.addWidget(widget)
            self.widgetlist.append(widget)

    def setup(self):
        for widget in self.widgetlist:
            widget.setup()

    def get(self):
        return [widget.get() for widget in self.widgetlist]


class FormTabWidget(QtWidgets.QWidget):
    update_buttons = QtCore.Signal()

    def __init__(self, datalist, comment="", parent=None):
        super().__init__(parent)
        layout = QtWidgets.QVBoxLayout()
        self.tabwidget = QtWidgets.QTabWidget()
        layout.addWidget(self.tabwidget)
        layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(layout)
        self.widgetlist = []
        for data, title, comment in datalist:
            if len(data[0]) == 3:
                widget = FormComboWidget(data, comment=comment, parent=self)
            else:
                widget = FormWidget(data, with_margin=True, comment=comment,
                                    parent=self)
            index = self.tabwidget.addTab(widget, title)
            self.tabwidget.setTabToolTip(index, comment)
            self.widgetlist.append(widget)

    def setup(self):
        for widget in self.widgetlist:
            widget.setup()

    def get(self):
        return [widget.get() for widget in self.widgetlist]


class FormDialog(QtWidgets.QDialog):
    """Form Dialog"""
    def __init__(self, data, title="", comment="",
                 icon=None, parent=None, apply=None):
        super().__init__(parent)

        self.apply_callback = apply

        # Form
        if isinstance(data[0][0], (list, tuple)):
            self.formwidget = FormTabWidget(data, comment=comment,
                                            parent=self)
        elif len(data[0]) == 3:
            self.formwidget = FormComboWidget(data, comment=comment,
                                              parent=self)
        else:
            self.formwidget = FormWidget(data, comment=comment,
                                         parent=self)
        layout = QtWidgets.QVBoxLayout()
        layout.addWidget(self.formwidget)

        self.float_fields = []
        self.formwidget.setup()

        # Button box
        self.bbox = bbox = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton(
                    _to_int(QtWidgets.QDialogButtonBox.StandardButton.Ok) |
                    _to_int(QtWidgets.QDialogButtonBox.StandardButton.Cancel)
            ))
        self.formwidget.update_buttons.connect(self.update_buttons)
        if self.apply_callback is not None:
            apply_btn = bbox.addButton(
                QtWidgets.QDialogButtonBox.StandardButton.Apply)
            apply_btn.clicked.connect(self.apply)

        bbox.accepted.connect(self.accept)
        bbox.rejected.connect(self.reject)
        layout.addWidget(bbox)

        self.setLayout(layout)

        self.setWindowTitle(title)
        if not isinstance(icon, QtGui.QIcon):
            icon = QtWidgets.QWidget().style().standardIcon(
                QtWidgets.QStyle.SP_MessageBoxQuestion)
        self.setWindowIcon(icon)

    def register_float_field(self, field):
        self.float_fields.append(field)

    def update_buttons(self):
        valid = True
        for field in self.float_fields:
            if not is_edit_valid(field):
                valid = False
        for btn_type in ["Ok", "Apply"]:
            btn = self.bbox.button(
                getattr(QtWidgets.QDialogButtonBox.StandardButton,
                        btn_type))
            if btn is not None:
                btn.setEnabled(valid)

    def accept(self):
        self.data = self.formwidget.get()
        self.apply_callback(self.data)
        super().accept()

    def reject(self):
        self.data = None
        super().reject()

    def apply(self):
        self.apply_callback(self.formwidget.get())

    def get(self):
        """Return form result"""
        return self.data


def fedit(data, title="", comment="", icon=None, parent=None, apply=None):
    """
    Create form dialog

    data: datalist, datagroup
    title: str
    comment: str
    icon: QIcon instance
    parent: parent QWidget
    apply: apply callback (function)

    datalist: list/tuple of (field_name, field_value)
    datagroup: list/tuple of (datalist *or* datagroup, title, comment)

    -> one field for each member of a datalist
    -> one tab for each member of a top-level datagroup
    -> one page (of a multipage widget, each page can be selected with a combo
       box) for each member of a datagroup inside a datagroup

    Supported types for field_value:
      - int, float, str, bool
      - colors: in Qt-compatible text form, i.e. in hex format or name
                (red, ...) (automatically detected from a string)
      - list/tuple:
          * the first element will be the selected index (or value)
          * the other elements can be couples (key, value) or only values
    """

    # Create a QApplication instance if no instance currently exists
    # (e.g., if the module is used directly from the interpreter)
    if QtWidgets.QApplication.startingUp():
        _app = QtWidgets.QApplication([])
    dialog = FormDialog(data, title, comment, icon, parent, apply)

    if parent is not None:
        if hasattr(parent, "_fedit_dialog"):
            parent._fedit_dialog.close()
        parent._fedit_dialog = dialog

    dialog.show()


if __name__ == "__main__":

    _app = QtWidgets.QApplication([])

    def create_datalist_example():
        return [('str', 'this is a string'),
                ('list', [0, '1', '3', '4']),
                ('list2', ['--', ('none', 'None'), ('--', 'Dashed'),
                           ('-.', 'DashDot'), ('-', 'Solid'),
                           ('steps', 'Steps'), (':', 'Dotted')]),
                ('float', 1.2),
                (None, 'Other:'),
                ('int', 12),
                ('font', ('Arial', 10, False, True)),
                ('color', '#123409'),
                ('bool', True),
                ('date', datetime.date(2010, 10, 10)),
                ('datetime', datetime.datetime(2010, 10, 10)),
                ]

    def create_datagroup_example():
        datalist = create_datalist_example()
        return ((datalist, "Category 1", "Category 1 comment"),
                (datalist, "Category 2", "Category 2 comment"),
                (datalist, "Category 3", "Category 3 comment"))

    # --------- datalist example
    datalist = create_datalist_example()

    def apply_test(data):
        print("data:", data)
    fedit(datalist, title="Example",
          comment="This is just an <b>example</b>.",
          apply=apply_test)

    _app.exec()

    # --------- datagroup example
    datagroup = create_datagroup_example()
    fedit(datagroup, "Global title",
          apply=apply_test)
    _app.exec()

    # --------- datagroup inside a datagroup example
    datalist = create_datalist_example()
    datagroup = create_datagroup_example()
    fedit(((datagroup, "Title 1", "Tab 1 comment"),
           (datalist, "Title 2", "Tab 2 comment"),
           (datalist, "Title 3", "Tab 3 comment")),
          "Global title",
          apply=apply_test)
    _app.exec()
