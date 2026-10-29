"""The Alarm on a staff page: a banner that stays, the open-Alarm count in the tab title
and favicon, and the chime repeating until someone Acknowledges (ADR-0010).

Each staff page includes `alarm_banner(...)` once, before its own scripts. The banner's
script opens the page's one event stream (`window.staffEvents`), which the Live view's
scripts then share. Inline on purpose: no external script, style, or sound (ADR-0006);
the chime is the assistant's own `/staff/alarm/chime.wav`. Event text is set with
textContent, never parsed as HTML.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime

from library_assistant.alarms import (
    chime_settings,
    open_flag_count,
    replays_on_page_open,
    unacknowledged_alarms,
    unacknowledged_escalations,
)
from library_assistant.staff import StaffAccount

CHIME_URL = "/staff/alarm/chime.wav"

ALARM_SCRIPT = """<script>
(() => {
  const config = JSON.parse(document.getElementById("alarm-config").textContent);
  const source = window.staffEvents || (window.staffEvents = new EventSource(config.events));
  const box = document.getElementById("alarms");
  const count = document.getElementById("open-flags");
  const chime = new Audio(config.chime);
  const title = document.title;
  const open = new Map();
  let repeat = null;
  // A browser refuses sound before the page's first click; the banner still shows.
  const play = () => {
    if (config.chime_on) chime.play().catch(() => {});
  };
  window.alarmChime = play;
  const icon = () => {
    let link = document.querySelector('link[rel="icon"]');
    if (!link) {
      link = document.createElement("link");
      link.rel = "icon";
      document.head.append(link);
    }
    return link;
  };
  // The favicon while an Alarm is open, drawn here so nothing is fetched.
  const redDot = () => {
    const canvas = document.createElement("canvas");
    canvas.width = canvas.height = 16;
    const context = canvas.getContext("2d");
    context.fillStyle = "red";
    context.beginPath();
    context.arc(8, 8, 8, 0, 2 * Math.PI);
    context.fill();
    return canvas.toDataURL();
  };
  const update = () => {
    document.title = open.size ? "(" + open.size + ") Alarm - " + title : title;
    icon().href = open.size ? redDot() : "data:,";
    if (open.size && config.chime_on && config.repeat_seconds > 0) {
      if (repeat === null) repeat = setInterval(play, config.repeat_seconds * 1000);
    } else if (repeat !== null) {
      clearInterval(repeat);
      repeat = null;
    }
  };
  const silence = (id) => {
    const div = open.get(id);
    if (!div) return;
    div.remove();
    open.delete(id);
    update();
  };
  const show = (data) => {
    if (open.has(data.flag_id)) return;
    const div = document.createElement("div");
    div.className = "alarm";
    div.dataset.flagId = data.flag_id;
    const what = document.createElement("p");
    what.textContent =
      config.label + ": " +
      data.severity + " " + data.category + " (" + data.source + "), " +
      data.class_label + " \\u00b7 card " + data.card_number +
      (data.registered_by ? ", registered by " + data.registered_by : "") +
      ", raised " + data.raised_at +
      (data.raised_unwatched ? ", raised unwatched" : "");
    const link = document.createElement("a");
    link.href = data.url;
    link.textContent = "Open the Flag";
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = "Acknowledge";
    button.addEventListener("click", () => {
      fetch(config.acknowledge + encodeURIComponent(data.flag_id) + "/acknowledge", {
        method: "POST",
        credentials: "same-origin",
      }).then((response) => {
        if (response.ok) silence(data.flag_id);
      });
    });
    div.append(what, link, " ", button);
    box.append(div);
    open.set(data.flag_id, div);
    play();
    update();
  };
  source.addEventListener(config.alarm_event, (event) => show(JSON.parse(event.data)));
  source.addEventListener("silenced", (event) => {
    const data = JSON.parse(event.data);
    if (Boolean(data.escalation) === config.escalation) silence(data.flag_id);
  });
  if (count) {
    source.addEventListener("flag_count", (event) => {
      count.textContent = String(JSON.parse(event.data).open);
    });
  }
  // Start watch hands back the unacknowledged Alarms, shown before anything else.
  document.addEventListener("alarm-replay", (event) => event.detail.forEach(show));
  config.pending.forEach(show);
})();
</script>"""


def _json_for_script(value: object) -> str:
    """JSON safe inside a <script> element: no `</script>` can close it early."""
    return (
        json.dumps(value)
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )


def _render(config: dict, count_line: str) -> str:
    return (
        '<div id="alarms" role="alert" aria-live="assertive"></div>'
        f"{count_line}"
        '<script type="application/json" id="alarm-config">'
        f"{_json_for_script(config)}</script>"
        f"{ALARM_SCRIPT}"
    )


def alarm_banner(db: sqlite3.Connection, account: StaffAccount, now: datetime) -> str:
    """The Alarm for this staff page, by role: the Librarian and a Stand-in hear every
    high-severity Flag on the Live view's stream; a Counselor hears only Escalated
    Flags, on the Counselor stream; anyone else gets nothing."""
    chime_on, repeat_seconds = chime_settings(db)
    config = {
        "chime": CHIME_URL,
        "chime_on": chime_on,
        "repeat_seconds": repeat_seconds,
    }
    if account.role == "librarian" or account.is_stand_in:
        pending = (
            unacknowledged_alarms(db)
            if replays_on_page_open(db, account.id, now)
            else []
        )
        config |= {
            "events": "/staff/live/events",
            "alarm_event": "alarm",
            "acknowledge": "/staff/alarms/",
            "escalation": False,
            "label": "Alarm",
            "pending": pending,
        }
        count_line = (
            '<p id="open-flags-line">Open Flags: '
            f'<span id="open-flags">{open_flag_count(db)}</span></p>'
        )
        return _render(config, count_line)
    if account.role == "counselor":
        config |= {
            "events": "/staff/counselor/events",
            "alarm_event": "escalated",
            "acknowledge": "/staff/counselor/alarms/",
            "escalation": True,
            "label": "Escalated Flag",
            "pending": unacknowledged_escalations(db),
        }
        return _render(config, "")
    return ""
