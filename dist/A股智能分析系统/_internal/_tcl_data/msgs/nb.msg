# created by tools/loadICU.tcl -- do not edit
namespace eval ::tcl::clock {
    ::msgcat::mcset nb DAYS_OF_WEEK_ABBREV [list \
        "s\u00f8"\
        "ma"\
        "ti"\
        "on"\
        "to"\
        "fr"\
        "l\u00f8"]
    ::msgcat::mcset nb DAYS_OF_WEEK_FULL [list \
        "s\u00f8ndag"\
        "mandag"\
        "tirsdag"\
        "onsdag"\
        "torsdag"\
        "fredag"\
        "l\u00f8rdag"]
    ::msgcat::mcset nb MONTHS_ABBREV [list \
        "jan"\
        "feb"\
        "mar"\
        "apr"\
        "mai"\
        "jun"\
        "jul"\
        "aug"\
        "sep"\
        "okt"\
        "nov"\
        "des"\
        ""]
    ::msgcat::mcset nb MONTHS_FULL [list \
        "januar"\
        "februar"\
        "mars"\
        "april"\
        "mai"\
        "juni"\
        "juli"\
        "august"\
        "september"\
        "oktober"\
        "november"\
        "desember"\
        ""]
    ::msgcat::mcset nb BCE "f.Kr."
    ::msgcat::mcset nb CE "e.Kr."
    ::msgcat::mcset nb DATE_FORMAT "%e. %B %Y"
    ::msgcat::mcset nb TIME_FORMAT "%H:%M:%S"
    ::msgcat::mcset nb DATE_TIME_FORMAT "%e. %B %Y %H:%M:%S %z"
}
