import datetime
import numpy as np

import pytest

import matplotlib.pyplot as plt
import matplotlib as mpl


class TestDatetimePlotting:
    @mpl.style.context("default")
    def test_annotate(self):
        mpl.rcParams["date.converter"] = 'concise'
        fig, (ax1, ax2, ax3, ax4) = plt.subplots(4, 1, layout="constrained")

        start_date = datetime.datetime(2023, 10, 1)
        dates = [start_date + datetime.timedelta(days=i) for i in range(31)]
        data = list(range(1, 32))
        test_text = "Test Text"

        ax1.plot(dates, data)
        ax1.annotate(text=test_text, xy=(dates[15], data[15]))
        ax2.plot(data, dates)
        ax2.annotate(text=test_text, xy=(data[5], dates[26]))
        ax3.plot(dates, dates)
        ax3.annotate(text=test_text, xy=(dates[15], dates[3]))
        ax4.plot(dates, dates)
        ax4.annotate(text=test_text, xy=(dates[5], dates[30]),
                        xytext=(dates[1], dates[7]), arrowprops=dict(facecolor='red'))

    @pytest.mark.xfail(reason="Test for arrow not written yet")
    @mpl.style.context("default")
    def test_arrow(self):
        fig, ax = plt.subplots()
        ax.arrow(...)

    @mpl.style.context("default")
    def test_axhline(self):
        mpl.rcParams["date.converter"] = 'concise'
        fig, (ax1, ax2, ax3) = plt.subplots(3, 1, layout='constrained')
        ax1.set_ylim(bottom=datetime.datetime(2020, 4, 1),
                     top=datetime.datetime(2020, 8, 1))
        ax2.set_ylim(bottom=np.datetime64('2005-01-01'),
                     top=np.datetime64('2005-04-01'))
        ax3.set_ylim(bottom=datetime.datetime(2023, 9, 1),
                     top=datetime.datetime(2023, 11, 1))
        ax1.axhline(y=datetime.datetime(2020, 6, 3), xmin=0.5, xmax=0.7)
        ax2.axhline(np.datetime64('2005-02-25T03:30'), xmin=0.1, xmax=0.9)
        ax3.axhline(y=datetime.datetime(2023, 10, 24), xmin=0.4, xmax=0.7)

    @mpl.style.context("default")
    def test_axhspan(self):
        mpl.rcParams["date.converter"] = 'concise'

        start_date = datetime.datetime(2023, 1, 1)
        dates = [start_date + datetime.timedelta(days=i) for i in range(31)]
        numbers = list(range(1, 32))

        fig, (ax1, ax2, ax3) = plt.subplots(3, 1,
                                            constrained_layout=True,
                                            figsize=(10, 12))

        ax1.plot(dates, numbers, marker='o', color='blue')
        for i in range(0, 31, 2):
            ax1.axhspan(ymin=i+1, ymax=i+2, facecolor='green', alpha=0.5)
        ax1.set_title('Datetime vs. Number')
        ax1.set_xlabel('Date')
        ax1.set_ylabel('Number')

        ax2.plot(numbers, dates, marker='o', color='blue')
        for i in range(0, 31, 2):
            ymin = start_date + datetime.timedelta(days=i)
            ymax = ymin + datetime.timedelta(days=1)
            ax2.axhspan(ymin=ymin, ymax=ymax, facecolor='green', alpha=0.5)
        ax2.set_title('Number vs. Datetime')
        ax2.set_xlabel('Number')
        ax2.set_ylabel('Date')

        ax3.plot(dates, dates, marker='o', color='blue')
        for i in range(0, 31, 2):
            ymin = start_date + datetime.timedelta(days=i)
            ymax = ymin + datetime.timedelta(days=1)
            ax3.axhspan(ymin=ymin, ymax=ymax, facecolor='green', alpha=0.5)
        ax3.set_title('Datetime vs. Datetime')
        ax3.set_xlabel('Date')
        ax3.set_ylabel('Date')

    @pytest.mark.xfail(reason="Test for axline not written yet")
    @mpl.style.context("default")
    def test_axline(self):
        fig, ax = plt.subplots()
        ax.axline(...)

    @mpl.style.context("default")
    def test_axvline(self):
        mpl.rcParams["date.converter"] = 'concise'
        fig, (ax1, ax2, ax3) = plt.subplots(3, 1, layout='constrained')
        ax1.set_xlim(left=datetime.datetime(2020, 4, 1),
                     right=datetime.datetime(2020, 8, 1))
        ax2.set_xlim(left=np.datetime64('2005-01-01'),
                     right=np.datetime64('2005-04-01'))
        ax3.set_xlim(left=datetime.datetime(2023, 9, 1),
                     right=datetime.datetime(2023, 11, 1))
        ax1.axvline(x=datetime.datetime(2020, 6, 3), ymin=0.5, ymax=0.7)
        ax2.axvline(np.datetime64('2005-02-25T03:30'), ymin=0.1, ymax=0.9)
        ax3.axvline(x=datetime.datetime(2023, 10, 24), ymin=0.4, ymax=0.7)

    @mpl.style.context("default")
    def test_axvspan(self):
        mpl.rcParams["date.converter"] = 'concise'

        start_date = datetime.datetime(2023, 1, 1)
        dates = [start_date + datetime.timedelta(days=i) for i in range(31)]
        numbers = list(range(1, 32))

        fig, (ax1, ax2, ax3) = plt.subplots(3, 1,
                                            constrained_layout=True,
                                            figsize=(10, 12))

        ax1.plot(dates, numbers, marker='o', color='blue')
        for i in range(0, 31, 2):
            xmin = start_date + datetime.timedelta(days=i)
            xmax = xmin + datetime.timedelta(days=1)
            ax1.axvspan(xmin=xmin, xmax=xmax, facecolor='red', alpha=0.5)
        ax1.set_title('Datetime vs. Number')
        ax1.set_xlabel('Date')
        ax1.set_ylabel('Number')

        ax2.plot(numbers, dates, marker='o', color='blue')
        for i in range(0, 31, 2):
            ax2.axvspan(xmin=i+1, xmax=i+2, facecolor='red', alpha=0.5)
        ax2.set_title('Number vs. Datetime')
        ax2.set_xlabel('Number')
        ax2.set_ylabel('Date')

        ax3.plot(dates, dates, marker='o', color='blue')
        for i in range(0, 31, 2):
            xmin = start_date + datetime.timedelta(days=i)
            xmax = xmin + datetime.timedelta(days=1)
            ax3.axvspan(xmin=xmin, xmax=xmax, facecolor='red', alpha=0.5)
        ax3.set_title('Datetime vs. Datetime')
        ax3.set_xlabel('Date')
        ax3.set_ylabel('Date')

    @mpl.style.context("default")
    def test_bar(self):
        mpl.rcParams["date.converter"] = "concise"

        fig, (ax1, ax2) = plt.subplots(2, 1, layout="constrained")

        x_dates = np.array(
            [
                datetime.datetime(2020, 6, 30),
                datetime.datetime(2020, 7, 22),
                datetime.datetime(2020, 8, 3),
                datetime.datetime(2020, 9, 14),
            ],
            dtype=np.datetime64,
        )
        x_ranges = [8800, 2600, 8500, 7400]

        x = np.datetime64(datetime.datetime(2020, 6, 1))
        ax1.bar(x_dates, x_ranges, width=np.timedelta64(4, "D"))
        ax2.bar(np.arange(4), x_dates - x, bottom=x)

    @mpl.style.context("default")
    def test_bar_label(self):
        # Generate some example data with dateTime inputs
        date_list = [datetime.datetime(2023, 1, 1) +
                     datetime.timedelta(days=i) for i in range(5)]
        values = [10, 20, 15, 25, 30]

        # Creating the plot
        fig, ax = plt.subplots(1, 1, figsize=(10, 8), layout='constrained')
        bars = ax.bar(date_list, values)

        # Add labels to the bars using bar_label
        ax.bar_label(bars, labels=[f'{val}%' for val in values],
                     label_type='edge', color='black')

    @mpl.style.context("default")
    def test_barbs(self):
        plt.rcParams["date.converter"] = 'concise'

        start_date = datetime.datetime(2022, 2, 8, 22)
        dates = [start_date + datetime.timedelta(hours=i) for i in range(12)]

        numbers = np.sin(np.linspace(0, 2 * np.pi, 12))

        u = np.ones(12) * 10
        v = np.arange(0, 120, 10)

        fig, axes = plt.subplots(nrows=1, ncols=2, figsize=(12, 6))

        axes[0].barbs(dates, numbers, u, v, length=7)
        axes[0].set_title('Datetime vs. Numeric Data')
        axes[0].set_xlabel('Datetime')
        axes[0].set_ylabel('Numeric Data')

        axes[1].barbs(numbers, dates, u, v, length=7)
        axes[1].set_title('Numeric vs. Datetime Data')
        axes[1].set_xlabel('Numeric Data')
        axes[1].set_ylabel('Datetime')

    @mpl.style.context("default")
    def test_barh(self):
        mpl.rcParams["date.converter"] = 'concise'
        fig, (ax1, ax2) = plt.subplots(2, 1, layout='constrained')
        birth_date = np.array([datetime.datetime(2020, 4, 10),
                               datetime.datetime(2020, 5, 30),
                               datetime.datetime(2020, 10, 12),
                               datetime.datetime(2020, 11, 15)])
        year_start = datetime.datetime(2020, 1, 1)
        year_end = datetime.datetime(2020, 12, 31)
        age = [21, 53, 20, 24]
        ax1.set_xlabel('Age')
        ax1.set_ylabel('Birth Date')
        ax1.barh(birth_date, width=age, height=datetime.timedelta(days=10))
        ax2.set_xlim(left=year_start, right=year_end)
        ax2.set_xlabel('Birth Date')
        ax2.set_ylabel('Order of Birth Dates')
        ax2.barh(np.arange(4), birth_date-year_start, left=year_start)

    @pytest.mark.xfail(reason="Test for boxplot not written yet")
    @mpl.style.context("default")
    def test_boxplot(self):
        fig, ax = plt.subplots()
        ax.boxplot(...)

    @mpl.style.context("default")
    def test_broken_barh(self):
        # Horizontal bar plot with gaps
        mpl.rcParams["date.converter"] = 'concise'
        fig, ax = plt.subplots()

        ax.broken_barh([(datetime.datetime(2023, 1, 4), datetime.timedelta(days=2)),
                        (datetime.datetime(2023, 1, 8), datetime.timedelta(days=3))],
                        (10, 9), facecolors='tab:blue')
        ax.broken_barh([(datetime.datetime(2023, 1, 2), datetime.timedelta(days=1)),
                         (datetime.datetime(2023, 1, 4), datetime.timedelta(days=4))],
                         (20, 9), facecolors=('tab:red'))

    @mpl.style.context("default")
    def test_bxp(self):
        mpl.rcParams["date.converter"] = 'concise'
        fig, ax = plt.subplots()
        data = [{
            "med": datetime.datetime(2020, 1, 15),
            "q1": datetime.datetime(2020, 1, 10),
            "q3": datetime.datetime(2020, 1, 20),
            "whislo": datetime.datetime(2020, 1, 5),
            "whishi": datetime.datetime(2020, 1, 25),
            "fliers": [
                datetime.datetime(2020, 1, 3),
                datetime.datetime(2020, 1, 27)
            ]
        }]
        ax.bxp(data, orientation='horizontal')
        ax.xaxis.set_major_formatter(mpl.dates.DateFormatter("%Y-%m-%d"))
        ax.set_title('Box plot with datetime data')

    @pytest.mark.xfail(reason="Test for clabel not written yet")
    @mpl.style.context("default")
    def test_clabel(self):
        fig, ax = plt.subplots()
        ax.clabel(...)

    @mpl.style.context("default")
    def test_contour(self):
        mpl.rcParams["date.converter"] = "concise"
        range_threshold = 10
        fig, (ax1, ax2, ax3) = plt.subplots(3, 1, layout="constrained")

        x_dates = np.array(
            [datetime.datetime(2023, 10, delta) for delta in range(1, range_threshold)]
        )
        y_dates = np.array(
            [datetime.datetime(2023, 10, delta) for delta in range(1, range_threshold)]
        )
        x_ranges = np.array(range(1, range_threshold))
        y_ranges = np.array(range(1, range_threshold))

        X_dates, Y_dates = np.meshgrid(x_dates, y_dates)
        X_ranges, Y_ranges = np.meshgrid(x_ranges, y_ranges)

        Z_ranges = np.cos(X_ranges / 4) + np.sin(Y_ranges / 4)

        ax1.contour(X_dates, Y_dates, Z_ranges)
        ax2.contour(X_dates, Y_ranges, Z_ranges)
        ax3.contour(X_ranges, Y_dates, Z_ranges)

    @mpl.style.context("default")
    def test_contourf(self):
        mpl.rcParams["date.converter"] = "concise"
        range_threshold = 10
        fig, (ax1, ax2, ax3) = plt.subplots(3, 1, layout="constrained")

        x_dates = np.array(
            [datetime.datetime(2023, 10, delta) for delta in range(1, range_threshold)]
        )
        y_dates = np.array(
            [datetime.datetime(2023, 10, delta) for delta in range(1, range_threshold)]
        )
        x_ranges = np.array(range(1, range_threshold))
        y_ranges = np.array(range(1, range_threshold))

        X_dates, Y_dates = np.meshgrid(x_dates, y_dates)
        X_ranges, Y_ranges = np.meshgrid(x_ranges, y_ranges)

        Z_ranges = np.cos(X_ranges / 4) + np.sin(Y_ranges / 4)

        ax1.contourf(X_dates, Y_dates, Z_ranges)
        ax2.contourf(X_dates, Y_ranges, Z_ranges)
        ax3.contourf(X_ranges, Y_dates, Z_ranges)

    @mpl.style.context("default")
    def test_errorbar(self):
        mpl.rcParams["date.converter"] = "concise"
        fig, (ax1, ax2, ax3, ax4) = plt.subplots(4, 1, layout="constrained")
        limit = 7
        start_date = datetime.datetime(2023, 1, 1)

        x_dates = np.array([datetime.datetime(2023, 10, d) for d in range(1, limit)])
        y_dates = np.array([datetime.datetime(2023, 10, d) for d in range(1, limit)])
        x_date_error = datetime.timedelta(days=1)
        y_date_error = datetime.timedelta(days=1)

        x_values = list(range(1, limit))
        y_values = list(range(1, limit))
        x_value_error = 0.5
        y_value_error = 0.5

        ax1.errorbar(x_dates, y_values,
                     yerr=y_value_error,
                     capsize=10,
                     barsabove=True,
                     label='Data')
        ax2.errorbar(x_values, y_dates,
                     xerr=x_value_error, yerr=y_date_error,
                     errorevery=(1, 2),
                     fmt='-o', label='Data')
        ax3.errorbar(x_dates, y_dates,
                     xerr=x_date_error, yerr=y_date_error,
                     lolims=True, xlolims=True,
                     label='Data')
        ax4.errorbar(x_dates, y_values,
                     xerr=x_date_error, yerr=y_value_error,
                     uplims=True, xuplims=True,
                     label='Data')

    @mpl.style.context("default")
    def test_eventplot(self):
        mpl.rcParams["date.converter"] = "concise"

        fig, (ax1, ax2, ax3) = plt.subplots(3, 1, layout="constrained")

        x_dates1 = np.array([datetime.datetime(2020, 6, 30),
                             datetime.datetime(2020, 7, 22),
                             datetime.datetime(2020, 8, 3),
                             datetime.datetime(2020, 9, 14),],
                            dtype=np.datetime64,
                            )

        ax1.eventplot(x_dates1)

        np.random.seed(19680801)

        start_date = datetime.datetime(2020, 7, 1)
        end_date = datetime.datetime(2020, 10, 15)
        date_range = end_date - start_date

        dates1 = start_date + np.random.rand(30) * date_range
        dates2 = start_date + np.random.rand(10) * date_range
        dates3 = start_date + np.random.rand(50) * date_range

        colors1 = ['C1', 'C2', 'C3']
        lineoffsets1 = np.array([1, 6, 8])
        linelengths1 = [5, 2, 3]

        ax2.eventplot([dates1, dates2, dates3],
                      colors=colors1,
                      lineoffsets=lineoffsets1,
                      linelengths=linelengths1)

        lineoffsets2 = np.array([
            datetime.datetime(2020, 7, 1),
            datetime.datetime(2020, 7, 15),
            datetime.datetime(2020, 8, 1)
        ], dtype=np.datetime64)

        ax3.eventplot([dates1, dates2, dates3],
                      colors=colors1,
                      lineoffsets=lineoffsets2,
                      linelengths=linelengths1)

    @mpl.style.context("default")
    def test_fill(self):
        mpl.rcParams["date.converter"] = "concise"
        fig, (ax1, ax2, ax3, ax4) = plt.subplots(4, 1, layout="constrained")

        np.random.seed(19680801)

        x_base_date = datetime.datetime(2023, 1, 1)
        x_dates = [x_base_date]
        for _ in range(1, 5):
            x_base_date += datetime.timedelta(days=np.random.randint(1, 5))
            x_dates.append(x_base_date)

        y_base_date = datetime.datetime(2023, 1, 1)
        y_dates = [y_base_date]
        for _ in range(1, 5):
            y_base_date += datetime.timedelta(days=np.random.randint(1, 5))
            y_dates.append(y_base_date)

        x_values = np.random.rand(5) * 5
        y_values = np.random.rand(5) * 5 - 2

        ax1.fill(x_dates, y_values)
        ax2.fill(x_values, y_dates)
        ax3.fill(x_values, y_values)
        ax4.fill(x_dates, y_dates)

    @mpl.style.context("default")
    def test_fill_between(self):
        mpl.rcParams["date.converter"] = "concise"
        np.random.seed(19680801)

        y_base_date = datetime.datetime(2023, 1, 1)
        y_dates1 = [y_base_date]
        for i in range(1, 10):
            y_base_date += datetime.timedelta(days=np.random.randint(1, 5))
            y_dates1.append(y_base_date)

        y_dates2 = [y_base_date]
        for i in range(1, 10):
            y_base_date += datetime.timedelta(days=np.random.randint(1, 5))
            y_dates2.append(y_base_date)
        x_values = np.random.rand(10) * 10
        x_values.sort()

        y_values1 = np.random.rand(10) * 10
        y_values2 = y_values1 + np.random.rand(10) * 10
        y_values1.sort()
        y_values2.sort()

        x_base_date = datetime.datetime(2023, 1, 1)
        x_dates = [x_base_date]
        for i in range(1, 10):
            x_base_date += datetime.timedelta(days=np.random.randint(1, 10))
            x_dates.append(x_base_date)

        fig, (ax1, ax2, ax3) = plt.subplots(3, 1, layout="constrained")

        ax1.fill_between(x_values, y_dates1, y_dates2)
        ax2.fill_between(x_dates, y_values1, y_values2)
        ax3.fill_between(x_dates, y_dates1, y_dates2)

    @mpl.style.context("default")
    def test_fill_betweenx(self):
        mpl.rcParams["date.converter"] = "concise"
        np.random.seed(19680801)

        x_base_date = datetime.datetime(2023, 1, 1)
        x_dates1 = [x_base_date]
        for i in range(1, 10):
            x_base_date += datetime.timedelta(days=np.random.randint(1, 5))
            x_dates1.append(x_base_date)

        x_dates2 = [x_base_date]
        for i in range(1, 10):
            x_base_date += datetime.timedelta(days=np.random.randint(1, 5))
            x_dates2.append(x_base_date)
        y_values = np.random.rand(10) * 10
        y_values.sort()

        x_values1 = np.random.rand(10) * 10
        x_values2 = x_values1 + np.random.rand(10) * 10
        x_values1.sort()
        x_values2.sort()

        y_base_date = datetime.datetime(2023, 1, 1)
        y_dates = [y_base_date]
        for i in range(1, 10):
            y_base_date += datetime.timedelta(days=np.random.randint(1, 10))
            y_dates.append(y_base_date)

        fig, (ax1, ax2, ax3) = plt.subplots(1, 3, layout="constrained")

        ax1.fill_betweenx(y_values, x_dates1, x_dates2)
        ax2.fill_betweenx(y_dates, x_values1, x_values2)
        ax3.fill_betweenx(y_dates, x_dates1, x_dates2)

    @pytest.mark.xfail(reason="Test for hexbin not written yet")
    @mpl.style.context("default")
    def test_hexbin(self):
        fig, ax = plt.subplots()
        ax.hexbin(...)

    @mpl.style.context("default")
    def test_hist(self):
        mpl.rcParams["date.converter"] = 'concise'

        start_date = datetime.datetime(2023, 10, 1)
        time_delta = datetime.timedelta(days=1)

        values1 = np.random.randint(1, 10, 30)
        values2 = np.random.randint(1, 10, 30)
        values3 = np.random.randint(1, 10, 30)

        bin_edges = [start_date + i * time_delta for i in range(31)]

        fig, (ax1, ax2, ax3) = plt.subplots(3, 1, constrained_layout=True)
        ax1.hist(
            [start_date + i * time_delta for i in range(30)],
            bins=10,
            weights=values1
        )
        ax2.hist(
            [start_date + i * time_delta for i in range(30)],
            bins=10,
            weights=values2
        )
        ax3.hist(
            [start_date + i * time_delta for i in range(30)],
            bins=10,
            weights=values3
        )

        fig, (ax4, ax5, ax6) = plt.subplots(3, 1, constrained_layout=True)
        ax4.hist(
            [start_date + i * time_delta for i in range(30)],
            bins=bin_edges,
            weights=values1
        )
        ax5.hist(
            [start_date + i * time_delta for i in range(30)],
            bins=bin_edges,
            weights=values2
        )
        ax6.hist(
            [start_date + i * time_delta for i in range(30)],
            bins=bin_edges,
            weights=values3
        )

    @pytest.mark.xfail(reason="Test for hist2d not written yet")
    @mpl.style.context("default")
    def test_hist2d(self):
        fig, ax = plt.subplots()
        ax.hist2d(...)

    @mpl.style.context("default")
    def test_hlines(self):
        mpl.rcParams["date.converter"] = 'concise'
        fig, axs = plt.subplots(2, 4, layout='constrained')
        dateStrs = ['2023-03-08',
                    '2023-04-09',
                    '2023-05-13',
                    '2023-07-28',
                    '2023-12-24']
        dates = [datetime.datetime(2023, m*2, 10) for m in range(1, 6)]
        date_start = [datetime.datetime(2023, 6, d) for d in range(5, 30, 5)]
        date_end = [datetime.datetime(2023, 7, d) for d in range(5, 30, 5)]
        npDates = [np.datetime64(s) for s in dateStrs]
        axs[0, 0].hlines(y=dates,
                         xmin=[0.1, 0.2, 0.3, 0.4, 0.5],
                         xmax=[0.5, 0.6, 0.7, 0.8, 0.9])
        axs[0, 1].hlines(dates,
                         xmin=datetime.datetime(2020, 5, 10),
                         xmax=datetime.datetime(2020, 5, 31))
        axs[0, 2].hlines(dates,
                         xmin=date_start,
                         xmax=date_end)
        axs[0, 3].hlines(dates,
                         xmin=0.45,
                         xmax=0.65)
        axs[1, 0].hlines(y=npDates,
                         xmin=[0.5, 0.6, 0.7, 0.8, 0.9],
                         xmax=[0.1, 0.2, 0.3, 0.4, 0.5])
        axs[1, 2].hlines(y=npDates,
                         xmin=date_start,
                         xmax=date_end)
        axs[1, 1].hlines(npDates,
                         xmin=datetime.datetime(2020, 5, 10),
                         xmax=datetime.datetime(2020, 5, 31))
        axs[1, 3].hlines(npDates,
                         xmin=0.45,
                         xmax=0.65)

    @mpl.style.context("default")
    def test_imshow(self):
        fig, ax = plt.subplots()
        a = np.diag(range(5))
        dt_start = datetime.datetime(2010, 11, 1)
        dt_end = datetime.datetime(2010, 11, 11)
        extent = (dt_start, dt_end, dt_start, dt_end)
        ax.imshow(a, extent=extent)
        ax.tick_params(axis="x", labelrotation=90)

    @pytest.mark.xfail(reason="Test for loglog not written yet")
    @mpl.style.context("default")
    def test_loglog(self):
        fig, ax = plt.subplots()
        ax.loglog(...)

    @mpl.style.context("default")
    def test_matshow(self):
        a = np.diag(range(5))
        dt_start = datetime.datetime(1980, 4, 15)
        dt_end = datetime.datetime(2020, 11, 11)
        extent = (dt_start, dt_end, dt_start, dt_end)
        fig, ax = plt.subplots()
        ax.matshow(a, extent=extent)
        for label in ax.get_xticklabels():
            label.set_rotation(90)

    @pytest.mark.xfail(reason="Test for pcolor not written yet")
    @mpl.style.context("default")
    def test_pcolor(self):
        fig, ax = plt.subplots()
        ax.pcolor(...)

    @pytest.mark.xfail(reason="Test for pcolorfast not written yet")
    @mpl.style.context("default")
    def test_pcolorfast(self):
        fig, ax = plt.subplots()
        ax.pcolorfast(...)

    @pytest.mark.xfail(reason="Test for pcolormesh not written yet")
    @mpl.style.context("default")
    def test_pcolormesh(self):
        fig, ax = plt.subplots()
        ax.pcolormesh(...)

    @mpl.style.context("default")
    def test_plot(self):
        mpl.rcParams["date.converter"] = 'concise'
        N = 6
        fig, (ax1, ax2, ax3) = plt.subplots(3, 1, layout='constrained')
        x = np.array([datetime.datetime(2023, 9, n) for n in range(1, N)])
        ax1.plot(x, range(1, N))
        ax2.plot(range(1, N), x)
        ax3.plot(x, x)

    @mpl.style.context("default")
    def test_plot_date(self):
        mpl.rcParams["date.converter"] = "concise"
        range_threshold = 10
        fig, (ax1, ax2, ax3) = plt.subplots(3, 1, layout="constrained")

        x_dates = np.array(
            [datetime.datetime(2023, 10, delta) for delta in range(1, range_threshold)]
        )
        y_dates = np.array(
            [datetime.datetime(2023, 10, delta) for delta in range(1, range_threshold)]
        )
        x_ranges = np.array(range(1, range_threshold))
        y_ranges = np.array(range(1, range_threshold))

        with pytest.warns(mpl.MatplotlibDeprecationWarning):
            ax1.plot_date(x_dates, y_dates)
            ax2.plot_date(x_dates, y_ranges)
            ax3.plot_date(x_ranges, y_dates)

    @pytest.mark.xfail(reason="Test for quiver not written yet")
    @mpl.style.context("default")
    def test_quiver(self):
        fig, ax = plt.subplots()
        ax.quiver(...)

    @mpl.style.context("default")
    def test_scatter(self):
        mpl.rcParams["date.converter"] = 'concise'
        base = datetime.datetime(2005, 2, 1)
        dates = [base + datetime.timedelta(hours=(2 * i)) for i in range(10)]
        N = len(dates)
        np.random.seed(19680801)
        y = np.cumsum(np.random.randn(N))
        fig, axs = plt.subplots(3, 1, layout='constrained', figsize=(6, 6))
        # datetime array on x axis
        axs[0].scatter(dates, y)
        for label in axs[0].get_xticklabels():
            label.set_rotation(40)
            label.set_horizontalalignment('right')
        # datetime on y axis
        axs[1].scatter(y, dates)
        # datetime on both x, y axes
        axs[2].scatter(dates, dates)
        for label in axs[2].get_xticklabels():
            label.set_rotation(40)
            label.set_horizontalalignment('right')

    @pytest.mark.xfail(reason="Test for semilogx not written yet")
    @mpl.style.context("default")
    def test_semilogx(self):
        fig, ax = plt.subplots()
        ax.semilogx(...)

    @pytest.mark.xfail(reason="Test for semilogy not written yet")
    @mpl.style.context("default")
    def test_semilogy(self):
        fig, ax = plt.subplots()
        ax.semilogy(...)

    @mpl.style.context("default")
    def test_stackplot(self):
        mpl.rcParams["date.converter"] = 'concise'
        N = 10
        stacked_nums = np.tile(np.arange(1, N), (4, 1))
        dates = np.array([datetime.datetime(2020 + i, 1, 1) for i in range(N - 1)])

        fig, ax = plt.subplots(layout='constrained')
        ax.stackplot(dates, stacked_nums)

    @mpl.style.context("default")
    def test_stairs(self):
        mpl.rcParams["date.converter"] = 'concise'

        start_date = datetime.datetime(2023, 12, 1)
        time_delta = datetime.timedelta(days=1)
        baseline_date = datetime.datetime(1980, 1, 1)

        bin_edges = [start_date + i * time_delta for i in range(31)]
        edge_int = np.arange(31)
        np.random.seed(123456)
        values1 = np.random.randint(1, 100, 30)
        values2 = [start_date + datetime.timedelta(days=int(i))
                   for i in np.random.randint(1, 10000, 30)]
        values3 = [start_date + datetime.timedelta(days=int(i))
                   for i in np.random.randint(-10000, 10000, 30)]

        fig, (ax1, ax2, ax3) = plt.subplots(3, 1, constrained_layout=True)
        ax1.stairs(values1, edges=bin_edges)
        ax2.stairs(values2, edges=edge_int, baseline=baseline_date)
        ax3.stairs(values3, edges=bin_edges, baseline=baseline_date)

    @mpl.style.context("default")
    def test_stem(self):
        mpl.rcParams["date.converter"] = "concise"

        fig, (ax1, ax2, ax3, ax4, ax5, ax6) = plt.subplots(6, 1, layout="constrained")

        limit_value = 10
        above = datetime.datetime(2023, 9, 18)
        below = datetime.datetime(2023, 11, 18)

        x_ranges = np.arange(1, limit_value)
        y_ranges = np.arange(1, limit_value)

        x_dates = np.array(
            [datetime.datetime(2023, 10, n) for n in range(1, limit_value)]
        )
        y_dates = np.array(
            [datetime.datetime(2023, 10, n) for n in range(1, limit_value)]
        )

        ax1.stem(x_dates, y_dates, bottom=above)
        ax2.stem(x_dates, y_ranges, bottom=5)
        ax3.stem(x_ranges, y_dates, bottom=below)

        ax4.stem(x_ranges, y_dates, orientation="horizontal", bottom=above)
        ax5.stem(x_dates, y_ranges, orientation="horizontal", bottom=5)
        ax6.stem(x_ranges, y_dates, orientation="horizontal", bottom=below)

    @mpl.style.context("default")
    def test_step(self):
        mpl.rcParams["date.converter"] = "concise"
        N = 6
        fig, (ax1, ax2, ax3) = plt.subplots(3, 1, layout='constrained')
        x = np.array([datetime.datetime(2023, 9, n) for n in range(1, N)])
        ax1.step(x, range(1, N))
        ax2.step(range(1, N), x)
        ax3.step(x, x)

    @pytest.mark.xfail(reason="Test for streamplot not written yet")
    @mpl.style.context("default")
    def test_streamplot(self):
        fig, ax = plt.subplots()
        ax.streamplot(...)

    @mpl.style.context("default")
    def test_text(self):
        mpl.rcParams["date.converter"] = 'concise'
        fig, (ax1, ax2, ax3) = plt.subplots(3, 1, layout="constrained")

        limit_value = 10
        font_properties = {'family': 'serif', 'size': 12, 'weight': 'bold'}
        test_date = datetime.datetime(2023, 10, 1)

        x_data = np.array(range(1, limit_value))
        y_data = np.array(range(1, limit_value))

        x_dates = np.array(
            [datetime.datetime(2023, 10, n) for n in range(1, limit_value)]
        )
        y_dates = np.array(
            [datetime.datetime(2023, 10, n) for n in range(1, limit_value)]
        )

        ax1.plot(x_dates, y_data)
        ax1.text(test_date, 5, "Inserted Text", **font_properties)

        ax2.plot(x_data, y_dates)
        ax2.text(7, test_date, "Inserted Text", **font_properties)

        ax3.plot(x_dates, y_dates)
        ax3.text(test_date, test_date, "Inserted Text", **font_properties)

    @pytest.mark.xfail(reason="Test for tricontour not written yet")
    @mpl.style.context("default")
    def test_tricontour(self):
        fig, ax = plt.subplots()
        ax.tricontour(...)

    @pytest.mark.xfail(reason="Test for tricontourf not written yet")
    @mpl.style.context("default")
    def test_tricontourf(self):
        fig, ax = plt.subplots()
        ax.tricontourf(...)

    @pytest.mark.xfail(reason="Test for tripcolor not written yet")
    @mpl.style.context("default")
    def test_tripcolor(self):
        fig, ax = plt.subplots()
        ax.tripcolor(...)

    @pytest.mark.xfail(reason="Test for triplot not written yet")
    @mpl.style.context("default")
    def test_triplot(self):
        fig, ax = plt.subplots()
        ax.triplot(...)

    @pytest.mark.xfail(reason="Test for violin not written yet")
    @mpl.style.context("default")
    def test_violin(self):
        fig, ax = plt.subplots()
        ax.violin(...)

    @pytest.mark.xfail(reason="Test for violinplot not written yet")
    @mpl.style.context("default")
    def test_violinplot(self):
        fig, ax = plt.subplots()
        ax.violinplot(...)

    @mpl.style.context("default")
    def test_vlines(self):
        mpl.rcParams["date.converter"] = 'concise'
        fig, (ax1, ax2, ax3) = plt.subplots(3, 1, layout='constrained')
        ax1.set_xlim(left=datetime.datetime(2023, 1, 1),
                     right=datetime.datetime(2023, 6, 30))
        ax1.vlines(x=[datetime.datetime(2023, 2, 10),
                      datetime.datetime(2023, 5, 18),
                      datetime.datetime(2023, 6, 6)],
                   ymin=[0, 0.25, 0.5],
                   ymax=[0.25, 0.5, 0.75])
        ax2.set_xlim(left=0,
                     right=0.5)
        ax2.vlines(x=[0.3, 0.35],
                   ymin=[np.datetime64('2023-03-20'), np.datetime64('2023-03-31')],
                   ymax=[np.datetime64('2023-05-01'), np.datetime64('2023-05-16')])
        ax3.set_xlim(left=datetime.datetime(2023, 7, 1),
                     right=datetime.datetime(2023, 12, 31))
        ax3.vlines(x=[datetime.datetime(2023, 9, 1), datetime.datetime(2023, 12, 10)],
                   ymin=datetime.datetime(2023, 1, 15),
                   ymax=datetime.datetime(2023, 1, 30))
