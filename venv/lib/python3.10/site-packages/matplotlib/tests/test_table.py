import datetime
from unittest.mock import Mock

import numpy as np

import matplotlib.pyplot as plt
from matplotlib.path import Path
from matplotlib.table import CustomCell, Table
from matplotlib.testing.decorators import image_comparison, check_figures_equal
from matplotlib.transforms import Bbox
import matplotlib.units as munits


def test_non_square():
    # Check that creating a non-square table works
    cellcolors = ['b', 'r']
    plt.table(cellColours=cellcolors)


@image_comparison(['table_zorder.png'], remove_text=True)
def test_zorder():
    data = [[66386, 174296],
            [58230, 381139]]

    colLabels = ('Freeze', 'Wind')
    rowLabels = ['%d year' % x for x in (100, 50)]

    cellText = []
    yoff = np.zeros(len(colLabels))
    for row in reversed(data):
        yoff += row
        cellText.append(['%1.1f' % (x/1000.0) for x in yoff])

    t = np.linspace(0, 2*np.pi, 100)
    plt.plot(t, np.cos(t), lw=4, zorder=2)

    plt.table(cellText=cellText,
              rowLabels=rowLabels,
              colLabels=colLabels,
              loc='center',
              zorder=-2,
              )

    plt.table(cellText=cellText,
              rowLabels=rowLabels,
              colLabels=colLabels,
              loc='upper center',
              zorder=4,
              )
    plt.yticks([])


@image_comparison(['table_labels.png'])
def test_label_colours():
    dim = 3

    c = np.linspace(0, 1, dim)
    colours = plt.cm.RdYlGn(c)
    cellText = [['1'] * dim] * dim

    fig = plt.figure()

    ax1 = fig.add_subplot(4, 1, 1)
    ax1.axis('off')
    ax1.table(cellText=cellText,
              rowColours=colours,
              loc='best')

    ax2 = fig.add_subplot(4, 1, 2)
    ax2.axis('off')
    ax2.table(cellText=cellText,
              rowColours=colours,
              rowLabels=['Header'] * dim,
              loc='best')

    ax3 = fig.add_subplot(4, 1, 3)
    ax3.axis('off')
    ax3.table(cellText=cellText,
              colColours=colours,
              loc='best')

    ax4 = fig.add_subplot(4, 1, 4)
    ax4.axis('off')
    ax4.table(cellText=cellText,
              colColours=colours,
              colLabels=['Header'] * dim,
              loc='best')


@image_comparison(['table_cell_manipulation.png'], style='mpl20')
def test_diff_cell_table(text_placeholders):
    cells = ('horizontal', 'vertical', 'open', 'closed', 'T', 'R', 'B', 'L')
    cellText = [['1'] * len(cells)] * 2
    colWidths = [0.1] * len(cells)

    _, axs = plt.subplots(nrows=len(cells), figsize=(4, len(cells)+1), layout='tight')
    for ax, cell in zip(axs, cells):
        ax.table(
                colWidths=colWidths,
                cellText=cellText,
                loc='center',
                edges=cell,
                )
        ax.axis('off')


def test_customcell():
    types = ('horizontal', 'vertical', 'open', 'closed', 'T', 'R', 'B', 'L')
    codes = (
        (Path.MOVETO, Path.LINETO, Path.MOVETO, Path.LINETO, Path.MOVETO),
        (Path.MOVETO, Path.MOVETO, Path.LINETO, Path.MOVETO, Path.LINETO),
        (Path.MOVETO, Path.MOVETO, Path.MOVETO, Path.MOVETO, Path.MOVETO),
        (Path.MOVETO, Path.LINETO, Path.LINETO, Path.LINETO, Path.CLOSEPOLY),
        (Path.MOVETO, Path.MOVETO, Path.MOVETO, Path.LINETO, Path.MOVETO),
        (Path.MOVETO, Path.MOVETO, Path.LINETO, Path.MOVETO, Path.MOVETO),
        (Path.MOVETO, Path.LINETO, Path.MOVETO, Path.MOVETO, Path.MOVETO),
        (Path.MOVETO, Path.MOVETO, Path.MOVETO, Path.MOVETO, Path.LINETO),
        )

    for t, c in zip(types, codes):
        cell = CustomCell((0, 0), visible_edges=t, width=1, height=1)
        code = tuple(s for _, s in cell.get_path().iter_segments())
        assert c == code


@image_comparison(['table_auto_column.png'])
def test_auto_column():
    fig, (ax1, ax2, ax3, ax4) = plt.subplots(4, 1)

    # iterable list input
    ax1.axis('off')
    tb1 = ax1.table(
        cellText=[['Fit Text', 2],
                  ['very long long text, Longer text than default', 1]],
        rowLabels=["A", "B"],
        colLabels=["Col1", "Col2"],
        loc="center")
    tb1.auto_set_font_size(False)
    tb1.set_fontsize(12)
    tb1.auto_set_column_width([-1, 0, 1])

    # iterable tuple input
    ax2.axis('off')
    tb2 = ax2.table(
        cellText=[['Fit Text', 2],
                  ['very long long text, Longer text than default', 1]],
        rowLabels=["A", "B"],
        colLabels=["Col1", "Col2"],
        loc="center")
    tb2.auto_set_font_size(False)
    tb2.set_fontsize(12)
    tb2.auto_set_column_width((-1, 0, 1))

    # 3 single inputs
    ax3.axis('off')
    tb3 = ax3.table(
        cellText=[['Fit Text', 2],
                  ['very long long text, Longer text than default', 1]],
        rowLabels=["A", "B"],
        colLabels=["Col1", "Col2"],
        loc="center")
    tb3.auto_set_font_size(False)
    tb3.set_fontsize(12)
    tb3.auto_set_column_width(-1)
    tb3.auto_set_column_width(0)
    tb3.auto_set_column_width(1)

    # 4 this used to test non-integer iterable input, which did nothing, but only
    # remains to avoid re-generating the test image.
    ax4.axis('off')
    tb4 = ax4.table(
        cellText=[['Fit Text', 2],
                  ['very long long text, Longer text than default', 1]],
        rowLabels=["A", "B"],
        colLabels=["Col1", "Col2"],
        loc="center")
    tb4.auto_set_font_size(False)
    tb4.set_fontsize(12)


def test_table_cells():
    fig, ax = plt.subplots()
    table = Table(ax)

    cell = table.add_cell(1, 2, 1, 1)
    assert isinstance(cell, CustomCell)
    assert cell is table[1, 2]

    cell2 = CustomCell((0, 0), 1, 2, visible_edges=None)
    table[2, 1] = cell2
    assert table[2, 1] is cell2

    # make sure getitem support has not broken
    # properties and setp
    table.properties()
    plt.setp(table)


@check_figures_equal(extensions=["png"])
def test_table_bbox(fig_test, fig_ref):
    data = [[2, 3],
            [4, 5]]

    col_labels = ('Foo', 'Bar')
    row_labels = ('Ada', 'Bob')

    cell_text = [[f"{x}" for x in row] for row in data]

    ax_list = fig_test.subplots()
    ax_list.table(cellText=cell_text,
                  rowLabels=row_labels,
                  colLabels=col_labels,
                  loc='center',
                  bbox=[0.1, 0.2, 0.8, 0.6]
                  )

    ax_bbox = fig_ref.subplots()
    ax_bbox.table(cellText=cell_text,
                  rowLabels=row_labels,
                  colLabels=col_labels,
                  loc='center',
                  bbox=Bbox.from_extents(0.1, 0.2, 0.9, 0.8)
                  )


@check_figures_equal(extensions=['png'])
def test_table_unit(fig_test, fig_ref):
    # test that table doesn't participate in unit machinery, instead uses repr/str

    class FakeUnit:
        def __init__(self, thing):
            pass
        def __repr__(self):
            return "Hello"

    fake_convertor = munits.ConversionInterface()
    # v, u, a = value, unit, axis
    fake_convertor.convert = Mock(side_effect=lambda v, u, a: 0)
    # not used, here for completeness
    fake_convertor.default_units = Mock(side_effect=lambda v, a: None)
    fake_convertor.axisinfo = Mock(side_effect=lambda u, a: munits.AxisInfo())

    munits.registry[FakeUnit] = fake_convertor

    data = [[FakeUnit("yellow"), FakeUnit(42)],
            [FakeUnit(datetime.datetime(1968, 8, 1)), FakeUnit(True)]]

    fig_test.subplots().table(data)
    fig_ref.subplots().table([["Hello", "Hello"], ["Hello", "Hello"]])
    fig_test.canvas.draw()
    fake_convertor.convert.assert_not_called()

    munits.registry.pop(FakeUnit)
    assert not munits.registry.get_converter(FakeUnit)


def test_table_dataframe(pd):
    # Test if Pandas Data Frame can be passed in cellText

    data = {
        'Letter': ['A', 'B', 'C'],
        'Number': [100, 200, 300]
    }

    df = pd.DataFrame(data)
    fig, ax = plt.subplots()
    table = ax.table(df, loc='center')

    for r, (index, row) in enumerate(df.iterrows()):
        for c, col in enumerate(df.columns if r == 0 else row.values):
            assert table[r if r == 0 else r+1, c].get_text().get_text() == str(col)


def test_table_fontsize():
    # Test that the passed fontsize propagates to cells
    tableData = [['a', 1], ['b', 2]]
    fig, ax = plt.subplots()
    test_fontsize = 20
    t = ax.table(cellText=tableData, loc='top', fontsize=test_fontsize)
    cell_fontsize = t[(0, 0)].get_fontsize()
    assert cell_fontsize == test_fontsize, f"Actual:{test_fontsize},got:{cell_fontsize}"
    cell_fontsize = t[(1, 1)].get_fontsize()
    assert cell_fontsize == test_fontsize, f"Actual:{test_fontsize},got:{cell_fontsize}"
