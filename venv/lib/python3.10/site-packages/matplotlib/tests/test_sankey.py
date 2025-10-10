import pytest
from numpy.testing import assert_allclose, assert_array_equal

from matplotlib.sankey import Sankey
from matplotlib.testing.decorators import check_figures_equal


def test_sankey():
    # lets just create a sankey instance and check the code runs
    sankey = Sankey()
    sankey.add()


def test_label():
    s = Sankey(flows=[0.25], labels=['First'], orientations=[-1])
    assert s.diagrams[0].texts[0].get_text() == 'First\n0.25'


def test_format_using_callable():
    # test using callable by slightly incrementing above label example

    def show_three_decimal_places(value):
        return f'{value:.3f}'

    s = Sankey(flows=[0.25], labels=['First'], orientations=[-1],
               format=show_three_decimal_places)

    assert s.diagrams[0].texts[0].get_text() == 'First\n0.250'


@pytest.mark.parametrize('kwargs, msg', (
    ({'gap': -1}, "'gap' is negative"),
    ({'gap': 1, 'radius': 2}, "'radius' is greater than 'gap'"),
    ({'head_angle': -1}, "'head_angle' is negative"),
    ({'tolerance': -1}, "'tolerance' is negative"),
    ({'flows': [1, -1], 'orientations': [-1, 0, 1]},
     r"The shapes of 'flows' \(2,\) and 'orientations'"),
    ({'flows': [1, -1], 'labels': ['a', 'b', 'c']},
     r"The shapes of 'flows' \(2,\) and 'labels'"),
    ))
def test_sankey_errors(kwargs, msg):
    with pytest.raises(ValueError, match=msg):
        Sankey(**kwargs)


@pytest.mark.parametrize('kwargs, msg', (
    ({'trunklength': -1}, "'trunklength' is negative"),
    ({'flows': [0.2, 0.3], 'prior': 0}, "The scaled sum of the connected"),
    ({'prior': -1}, "The index of the prior diagram is negative"),
    ({'prior': 1}, "The index of the prior diagram is 1"),
    ({'connect': (-1, 1), 'prior': 0}, "At least one of the connection"),
    ({'connect': (2, 1), 'prior': 0}, "The connection index to the source"),
    ({'connect': (1, 3), 'prior': 0}, "The connection index to this dia"),
    ({'connect': (1, 1), 'prior': 0, 'flows': [-0.2, 0.2],
      'orientations': [2]}, "The value of orientations"),
    ({'connect': (1, 1), 'prior': 0, 'flows': [-0.2, 0.2],
      'pathlengths': [2]}, "The lengths of 'flows'"),
    ))
def test_sankey_add_errors(kwargs, msg):
    sankey = Sankey()
    with pytest.raises(ValueError, match=msg):
        sankey.add(flows=[0.2, -0.2])
        sankey.add(**kwargs)


def test_sankey2():
    s = Sankey(flows=[0.25, -0.25, 0.5, -0.5], labels=['Foo'],
               orientations=[-1], unit='Bar')
    sf = s.finish()
    assert_array_equal(sf[0].flows, [0.25, -0.25, 0.5, -0.5])
    assert sf[0].angles == [1, 3, 1, 3]
    assert all([text.get_text()[0:3] == 'Foo' for text in sf[0].texts])
    assert all([text.get_text()[-3:] == 'Bar' for text in sf[0].texts])
    assert sf[0].text.get_text() == ''
    assert_allclose(sf[0].tips,
                    [(-1.375, -0.52011255),
                     (1.375, -0.75506044),
                     (-0.75, -0.41522509),
                     (0.75, -0.8599479)])

    s = Sankey(flows=[0.25, -0.25, 0, 0.5, -0.5], labels=['Foo'],
               orientations=[-1], unit='Bar')
    sf = s.finish()
    assert_array_equal(sf[0].flows, [0.25, -0.25, 0, 0.5, -0.5])
    assert sf[0].angles == [1, 3, None, 1, 3]
    assert_allclose(sf[0].tips,
                    [(-1.375, -0.52011255),
                     (1.375, -0.75506044),
                     (0, 0),
                     (-0.75, -0.41522509),
                     (0.75, -0.8599479)])


@check_figures_equal(extensions=['png'])
def test_sankey3(fig_test, fig_ref):
    ax_test = fig_test.gca()
    s_test = Sankey(ax=ax_test, flows=[0.25, -0.25, -0.25, 0.25, 0.5, -0.5],
                    orientations=[1, -1, 1, -1, 0, 0])
    s_test.finish()

    ax_ref = fig_ref.gca()
    s_ref = Sankey(ax=ax_ref)
    s_ref.add(flows=[0.25, -0.25, -0.25, 0.25, 0.5, -0.5],
              orientations=[1, -1, 1, -1, 0, 0])
    s_ref.finish()
