# Unused placeholder

`firebase.json`'s hosting config rewrites every path (`**`) to the Cloud Run
service, so nothing in this directory is ever actually served — Firebase
Hosting's CLI just requires a `public` directory to exist at deploy time.
