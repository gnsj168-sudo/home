import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from plugins import Plugin

SCOPES = ["https://www.googleapis.com/auth/calendar.events"]
TZ = ZoneInfo("Asia/Kuala_Lumpur")
HOME_MARKER = "Added by Home"


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
        origin = " (added by Home)" if HOME_MARKER in (e.get("description") or "") else ""
        lines.append(f"- {label} - {e.get('summary', 'Untitled')}{origin}")

    return "\n".join(lines)


def create_event(summary: str, start: str, end: str = "", all_day: bool = False, force: bool = False) -> str:
    """Create a calendar event. YYYY-MM-DD for all-day, YYYY-MM-DDTHH:MM for timed."""
    if not force:
        try:
            day = start[:10]
            next_day = (datetime.strptime(day, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
            existing = list_events(day, next_day)
            if summary.lower() in existing.lower():
                return (
                    f"An event matching '{summary}' already exists on {day}:\n{existing}\n"
                    "Ask the user whether to add it anyway. If they confirm, call "
                    "create_event again with force set to true."
                )
        except Exception:
            pass

    try:
        if all_day:
            start_obj = {"date": start[:10]}
            end_date = (
                datetime.strptime(start[:10], "%Y-%m-%d") + timedelta(days=1)
            ).strftime("%Y-%m-%d")
            end_obj = {"date": end_date}
        else:
            start_dt = datetime.fromisoformat(start).replace(tzinfo=TZ)
            end_dt = (
                datetime.fromisoformat(end).replace(tzinfo=TZ)
                if end
                else start_dt + timedelta(hours=1)
            )
            start_obj = {"dateTime": start_dt.isoformat(), "timeZone": str(TZ)}
            end_obj = {"dateTime": end_dt.isoformat(), "timeZone": str(TZ)}
    except ValueError as e:
        return f"Could not parse the date or time: {e}"

    body = {
        "summary": summary,
        "start": start_obj,
        "end": end_obj,
        "description": f"{HOME_MARKER} on {datetime.now(TZ).strftime('%d %b %Y, %I:%M %p')}",
    }

    try:
        created = _service().events().insert(calendarId="primary", body=body).execute()
    except Exception as e:
        return f"Could not create the event: {e}"

    return f"Created '{summary}'."

CALENDAR_PLUGIN = Plugin(
    name="calendar",
    description="Read and write access to the user's Google Calendar.",
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
        },
        {
            "name": "create_event",
            "description": (
                "Create an event on the user's calendar. Use this whenever they ask "
                "to add, schedule, or book something with a date - never save it as a "
                "note instead. Call get_current_time first if the date is relative."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {"type": "string", "description": "Event title."},
                    "start": {
                        "type": "string",
                        "description": "YYYY-MM-DD for all-day, YYYY-MM-DDTHH:MM for timed.",
                    },
                    "end": {
                        "type": "string",
                        "description": "Optional end, YYYY-MM-DDTHH:MM. Defaults to one hour after start.",
                    },
                    "all_day": {"type": "boolean", "description": "True for all-day events."},
                    "force": {
                        "type": "boolean",
                        "description": "Set true only after the user confirms adding a duplicate.",
                    },
                },
                "required": ["summary", "start"],
            },
        },
    ],
    implementations={"list_events": list_events, "create_event": create_event},
    prompt_fragment=(
        "You can read and create calendar events. Calendar data is live - never "
        "answer schedule questions from notes. When the user asks to add or schedule "
        "something with a date, use create_event, not add_note."
    ),
)