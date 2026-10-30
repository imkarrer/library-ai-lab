"""The Open Flags panel on the watching pages (ADR-0010 amendment, lib-4m7).

Whoever is on Watch sees every open Flag the moment it is raised, low-severity included,
on the page they are already watching: one row per open Flag, high-severity first, each a
link to the Flag's page. A row shows what the Live view may show on a shared screen
(docs/design/live-view.md): severity, Class label, Card number, time, source, and its stage
(New, then Acknowledged, or Escalated once the Counselor owns it; a closed Flag
leaves the panel, lib-msq, lib-6n9); never the
category, the reason, or the Student's words, which are one click away. The rows follow the
page's one event stream (`window.staffEvents`, opened by the Alarm banner): `flag` adds a
row, `flag_closed` removes it, and both update the Session tile's Flag marker.
"""

from __future__ import annotations

import html
import sqlite3
from datetime import datetime
from zoneinfo import ZoneInfo

from library_assistant.alarms import panel_payload
from library_assistant.flags import open_flags

SOURCE_LABELS = {"watchlist": "Watchlist", "oversight": "Oversight"}

PANEL_SCRIPT = """<script>
(() => {
  const source = window.staffEvents || (window.staffEvents = new EventSource("/staff/live/events"));
  const list = document.getElementById("flag-list");
  const sources = { watchlist: "Watchlist", oversight: "Oversight" };
  const empty = () => {
    if (!list.querySelector(".flag-row") && !document.getElementById("no-flags")) {
      const none = document.createElement("li");
      none.id = "no-flags";
      none.textContent = "No open Flags.";
      list.append(none);
    }
  };
  const row = (data) => {
    const item = document.createElement("li");
    item.className = "flag-row flag-" + data.severity;
    item.dataset.flagId = String(data.flag_id);
    const link = document.createElement("a");
    link.href = data.url;
    const severity = document.createElement("strong");
    severity.textContent = data.severity === "high" ? "High" : "Low";
    const when = new Date(data.raised_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false });
    link.append(severity, " " + data.class_label + " \\u00b7 card " + data.card_number +
      " \\u00b7 " + when + " \\u00b7 " + (sources[data.source] || data.source) + " \\u00b7 ");
    const stage = document.createElement("span");
    stage.className = "stage";
    stage.textContent = data.escalated ? "Escalated" : data.acknowledged ? "Acknowledged" : "New";
    link.append(stage);
    item.append(link);
    return item;
  };
  // The tile's marker follows the highest severity still open on its Session.
  const mark = (data) => {
    if (data.session_no === null || data.session_no === undefined) return;
    const tile = document.querySelector('.tile[data-session-no="' + Number(data.session_no) + '"]');
    if (!tile) return;
    tile.classList.remove("flag-high", "flag-low");
    const old = tile.querySelector(".flag-badge");
    if (old) old.remove();
    if (!data.session_severity) return;
    tile.classList.add("flag-" + data.session_severity);
    const badge = document.createElement("span");
    badge.className = "flag-badge";
    badge.textContent = "Flag: " + data.session_severity;
    const latest = tile.querySelector(".latest");
    if (latest) latest.after(badge);
    else tile.querySelector("a").append(badge);
  };
  source.addEventListener("flag", (event) => {
    const data = JSON.parse(event.data);
    const none = document.getElementById("no-flags");
    if (none) none.remove();
    const existing = list.querySelector('[data-flag-id="' + Number(data.flag_id) + '"]');
    if (existing) existing.remove();
    const item = row(data);
    // High-severity rows stay above low ones; newest first within each.
    const highs = list.querySelectorAll(".flag-row.flag-high");
    if (data.severity === "high" || !highs.length) list.prepend(item);
    else highs[highs.length - 1].after(item);
    mark(data);
  });
  // Acknowledged anywhere (the Alarm banner, the Flag page, another adult's screen).
  source.addEventListener("silenced", (event) => {
    const data = JSON.parse(event.data);
    if (data.escalation) return;
    const stage = list.querySelector('[data-flag-id="' + Number(data.flag_id) + '"] .stage');
    if (stage && stage.textContent === "New") stage.textContent = "Acknowledged";
  });
  source.addEventListener("flag_closed", (event) => {
    const data = JSON.parse(event.data);
    const item = list.querySelector('[data-flag-id="' + Number(data.flag_id) + '"]');
    if (item) item.remove();
    empty();
    mark(data);
  });
})();
</script>"""


def _stage(row: dict) -> str:
    if row["escalated"]:
        return "Escalated"
    return "Acknowledged" if row["acknowledged"] else "New"


def _row_html(row: dict, timezone: str) -> str:
    raised = datetime.fromisoformat(row["raised_at"]).astimezone(ZoneInfo(timezone))
    severity = "High" if row["severity"] == "high" else "Low"
    who = (
        f"{html.escape(row['class_label'])} &middot; card "
        f"{html.escape(row['card_number'])} &middot; {raised:%H:%M} &middot; "
        f"{SOURCE_LABELS.get(row['source'], html.escape(row['source']))} &middot; "
        f'<span class="stage">{_stage(row)}</span>'
    )
    return (
        f'<li class="flag-row flag-{html.escape(row["severity"])}" '
        f'data-flag-id="{row["flag_id"]}">'
        f'<a href="{html.escape(row["url"])}"><strong>{severity}</strong> {who}</a></li>'
    )


def flags_panel(db: sqlite3.Connection, timezone: str) -> str:
    """The panel as the page first draws it; the script keeps it current."""
    rows = [panel_payload(db, flag) for flag in open_flags(db)]
    rows.sort(key=lambda row: row["severity"] != "high")  # stable: newest first in each
    items = "".join(_row_html(row, timezone) for row in rows) or (
        '<li id="no-flags">No open Flags.</li>'
    )
    return (
        '<section id="open-flags-panel" aria-live="polite">'
        "<h2>Open Flags</h2>"
        f'<ul id="flag-list">{items}</ul></section>'
        f"{PANEL_SCRIPT}"
    )
