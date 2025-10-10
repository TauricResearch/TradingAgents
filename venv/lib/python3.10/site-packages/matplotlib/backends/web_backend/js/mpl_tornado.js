/* This .js file contains functions for matplotlib's built-in
   tornado-based server, that are not relevant when embedding WebAgg
   in another web application. */

/* exported mpl_ondownload */
function mpl_ondownload(figure, format) {
    window.open(figure.id + '/download.' + format, '_blank');
}
