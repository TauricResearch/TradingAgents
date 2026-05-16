import os


def get_config() -> dict:
    return {
        "serpapi_key": os.environ["SERPAPI_KEY"],
        "gmail_user": os.environ["GMAIL_USER"],
        "gmail_app_password": os.environ["GMAIL_APP_PASSWORD"],
        "alert_email": os.environ["ALERT_EMAIL"],
        "origin": os.environ["ORIGIN"],
        "destination": os.environ["DESTINATION"],
        "outbound_date": os.environ["OUTBOUND_DATE"],
        "return_date": os.environ["RETURN_DATE"],
    }
