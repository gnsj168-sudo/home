import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from plugins import Plugin

SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]
TZ = ZoneInfo("Asia/Kuala_Lumpur")


def _service():
    creds = None
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
            creds = flow.run_local_server(port=0)
        with open("token.json", "w") as f:
            f.write(creds.to_json())

    return build("calendar", "v3", credentials=creds)


def list_events(start_date: str, end_date: str) -> str:
    """List calendar events between two dates (YYYY-MM-DD, end exclusive)."""
    try:
        start = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=TZ)
        end = datetime.strptime(end_date, "%Y-%m-%d").replace(tzinfo=TZ)
    except ValueError:
        return "Dates must be in YYYY-MM-DD format."

    if end <= start:
        end = start + timedelta(days=1)

    try:
        events = (
            _service()
            .events()
            .list(
                calendarId="primary",
                timeMin=start.isoformat(),
                timeMax=end.isoformat(),
                singleEvents=True,
                orderBy="startTime",
                maxResults=50,
            )
            .execute()
            .get("items", [])
        )
    except Exception as e:
        return f"Could not reach the calendar: {e}"

    if not events:
        return f"No events between {start_date} and {end_date}."

    lines = []
    for e in events:
        when = e["start"].get("dateTime")
        if when:
            label = datetime.fromisoformat(when).astimezone(TZ).strftime("%a %d %b, %I:%M %p")
        else:
            label = datetime.strptime(e["start"]["date"], "%Y-%m-%d").strftime("%a %d %b (all day)")
        lines.append(f"- {label} — {e.get('summary', 'Untitled')}")

    return "\n".join(lines)


CALENDAR_PLUGIN = Plugin(
    name="calendar",
    description="Read-only access to the user's Google Calendar.",
    schemas=[
        {
            "name": "list_events",
            "description": (
                "List the user's calendar events in a date range. Call "
                "get_current_time first if the user says 'today', 'this week', "
                "or any other relative date, so you can compute real dates."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "start_date": {"type": "string", "description": "Start date, YYYY-MM-DD."},
                    "end_date": {"type": "string", "description": "End date, YYYY-MM-DD, exclusive."},
                },
                "required": ["start_date", "end_date"],
            },
        }
    ],
    implementations={"list_events": list_events},
    prompt_fragment=(
        "You can read the user's calendar with list_events. Calendar data is live — "
        "never answer schedule questions from notes or memory."
    ),
)