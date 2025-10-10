import numpy as np
import matplotlib as mpl
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker

__all__ = ["palplot", "dogplot"]


def palplot(pal, size=1):
    """Plot the values in a color palette as a horizontal array.

    Parameters
    ----------
    pal : sequence of matplotlib colors
        colors, i.e. as returned by seaborn.color_palette()
    size :
        scaling factor for size of plot

    """
    n = len(pal)
    _, ax = plt.subplots(1, 1, figsize=(n * size, size))
    ax.imshow(np.arange(n).reshape(1, n),
              cmap=mpl.colors.ListedColormap(list(pal)),
              interpolation="nearest", aspect="auto")
    ax.set_xticks(np.arange(n) - .5)
    ax.set_yticks([-.5, .5])
    # Ensure nice border between colors
    ax.set_xticklabels(["" for _ in range(n)])
    # The proper way to set no ticks
    ax.yaxis.set_major_locator(ticker.NullLocator())


def dogplot(*_, **__):
    """Who's a good boy?"""
    from urllib.request import urlopen
    from io import BytesIO

    url = "https://github.com/mwaskom/seaborn-data/raw/master/png/img{}.png"
    pic = np.random.randint(2, 7)
    data = BytesIO(urlopen(url.format(pic)).read())
    img = plt.imread(data)
    f, ax = plt.subplots(figsize=(5, 5), dpi=100)
    f.subplots_adjust(0, 0, 1, 1)
    ax.imshow(img)
    ax.set_axis_off()
