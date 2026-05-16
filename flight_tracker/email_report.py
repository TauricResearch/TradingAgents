import html as html_module
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


def _fmt_price(price) -> str:
    if price is None:
        return "N/A"
    return f"${price:,}"


def _fmt_duration(minutes: int) -> str:
    return f"{minutes // 60}h {minutes % 60}m"


def _flight_row(flight) -> dict:
    if flight is None:
        return {"price": "N/A", "airline": "N/A", "stops": "N/A", "duration": "N/A", "departs": "N/A"}
    return {
        "price": _fmt_price(flight.price),
        "airline": html_module.escape(flight.airline),
        "stops": str(flight.stops),
        "duration": _fmt_duration(flight.duration_min),
        "departs": html_module.escape(flight.departs),
    }


def _leg_table(title: str, picks: tuple) -> str:
    fewest, cheapest = picks
    f = _flight_row(fewest)
    c = _flight_row(cheapest)
    return f"""
<h2>{title}</h2>
<table border="1" cellpadding="6" cellspacing="0">
  <tr><th></th><th>Fewest Stops</th><th>Overall Cheapest</th></tr>
  <tr><td>Price</td><td>{f['price']}</td><td>{c['price']}</td></tr>
  <tr><td>Airline</td><td>{f['airline']}</td><td>{c['airline']}</td></tr>
  <tr><td>Stops</td><td>{f['stops']}</td><td>{c['stops']}</td></tr>
  <tr><td>Duration</td><td>{f['duration']}</td><td>{c['duration']}</td></tr>
  <tr><td>Departs</td><td>{f['departs']}</td><td>{c['departs']}</td></tr>
</table>
"""


def build_subject(outbound_picks: tuple, return_picks: tuple, today: str, origin: str, destination: str) -> str:
    fewest, cheapest = outbound_picks
    fewest_price = _fmt_price(fewest.price if fewest else None)
    cheapest_price = _fmt_price(cheapest.price if cheapest else None)
    # Strip control chars to prevent MIME header injection
    safe_origin = origin.translate({ord(c): None for c in "\r\n"})
    safe_dest = destination.translate({ord(c): None for c in "\r\n"})
    return f"✈ {safe_origin}→{safe_dest} | Fewest Stops: {fewest_price} | Cheapest: {cheapest_price} | {today}"


def build_html(outbound_picks: tuple, return_picks: tuple, today: str) -> str:
    outbound_table = _leg_table("Outbound", outbound_picks)
    return_table = _leg_table("Return", return_picks)
    return f"""<html><body>
{outbound_table}
{return_table}
<p><small>Searched via SerpAPI Google Flights &middot; History tracked in history.csv</small></p>
</body></html>"""


def send_email(html: str, subject: str, config: dict) -> None:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = config["gmail_user"]
    msg["To"] = config["alert_email"]
    msg.attach(MIMEText(html, "html"))

    ctx = ssl.create_default_context()
    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.ehlo()
        server.starttls(context=ctx)
        server.login(config["gmail_user"], config["gmail_app_password"])
        server.sendmail(config["gmail_user"], config["alert_email"], msg.as_string())
