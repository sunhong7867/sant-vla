#!/usr/bin/env python3
"""Generate a side-by-side viewer (view.html) for a scene_reasoning session.

Left pane: the log.csv rows. Right pane: the frame image for the selected row.
Click a row (or use Up/Down arrows) to switch the image.

Usage:
    python3 tools/scene_log_viewer.py <session_dir> [more session dirs...]
    python3 tools/scene_log_viewer.py --latest      # newest session under the default log root

Then open <session_dir>/view.html in a browser.
The CSV content is embedded at generation time; images are referenced by their
relative paths, so the file works over file:// with no server.
"""
import csv
import html
import json
import sys
from pathlib import Path

LOG_ROOT = Path("~/ROS2_project/sant-vla/src/sant_vla_pkg/logs/scene_reasoning").expanduser()

PAGE = """<!DOCTYPE html>
<html lang="ko" data-theme="dark">
<head>
<meta charset="utf-8">
<title>{title}</title>
<style>
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; font: 15px/1.5 "Noto Sans KR", sans-serif;
         background: #1e1e1e; color: #d4d4d4; height: 100vh;
         display: flex; overflow: hidden; }}
  #left {{ flex: 1 1 55%; overflow: auto; border-right: 1px solid #3c3c3c; }}
  #right {{ flex: 1 1 45%; display: flex; flex-direction: column;
            align-items: center; padding: 12px; overflow: auto; }}
  /* Frames are logged at 384px — stretch to the pane; the upscale blur is
     preferable to a thumbnail-sized image. */
  #right img {{ width: 100%; border: 1px solid #3c3c3c; }}
  #caption {{ margin-top: 10px; white-space: pre-wrap; color: #9cdcfe;
              font-size: 16px; align-self: stretch; }}
  table {{ border-collapse: collapse; width: 100%; }}
  th, td {{ border: 1px solid #333; padding: 3px 6px; text-align: left;
            vertical-align: top; }}
  th {{ position: sticky; top: 0; background: #252526; z-index: 1; }}
  tbody tr {{ cursor: pointer; }}
  tbody tr:hover {{ background: #2a2d2e; }}
  tbody tr.sel {{ background: #094771; }}
  td.facts {{ font-family: monospace; font-size: 12.5px; max-width: 340px;
              word-break: break-all; }}
  td.line {{ max-width: 280px; }}
  .kind-curve {{ color: #ce9178; }} .kind-straight {{ color: #b5cea8; }}
  .turn-left {{ color: #dcdcaa; font-weight: bold; }}
  .turn-right {{ color: #c586c0; font-weight: bold; }}
</style>
</head>
<body>
<div id="left">
<table>
<thead><tr><th>#</th><th>time</th><th>frame</th><th>kind</th><th>turn</th>
<th>dv</th><th class="facts">facts</th><th>shown_line</th></tr></thead>
<tbody id="rows">
{rows}
</tbody>
</table>
</div>
<div id="right">
  <img id="img" src="" alt="frame">
  <div id="caption"></div>
</div>
<script>
const rows = Array.from(document.querySelectorAll("#rows tr"));
let sel = -1;
function pick(i) {{
  if (i < 0 || i >= rows.length) return;
  if (sel >= 0) rows[sel].classList.remove("sel");
  sel = i;
  const r = rows[i];
  r.classList.add("sel");
  r.scrollIntoView({{ block: "nearest" }});
  document.getElementById("img").src = r.dataset.frame;
  document.getElementById("caption").textContent =
    r.dataset.frame + "\\n" + r.dataset.line;
}}
rows.forEach((r, i) => r.addEventListener("click", () => pick(i)));
document.addEventListener("keydown", e => {{
  if (e.key === "ArrowDown") {{ pick(sel + 1); e.preventDefault(); }}
  if (e.key === "ArrowUp")   {{ pick(sel - 1); e.preventDefault(); }}
}});
pick(0);
</script>
</body>
</html>
"""

ROW = ("<tr data-frame=\"{frame}\" data-line=\"{line_attr}\">"
       "<td>{seq}</td><td>{t}</td><td>{frame_short}</td>"
       "<td class=\"kind-{kind}\">{kind}</td>"
       "<td class=\"turn-{turn}\">{turn}</td><td>{dv}</td>"
       "<td class=\"facts\">{facts}</td><td class=\"line\">{line}</td></tr>")


def build(session_dir: Path) -> Path:
    log = session_dir / "log.csv"
    if not log.is_file():
        raise SystemExit(f"no log.csv in {session_dir}")
    out_rows = []
    with open(log, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            try:
                facts = json.loads(row.get("facts") or "{}")
            except json.JSONDecodeError:
                facts = {}
            frame = row.get("frame_file") or ""
            line = row.get("shown_line") or row.get("raw_line") or ""
            out_rows.append(ROW.format(
                frame=html.escape(frame, quote=True),
                line_attr=html.escape(line, quote=True),
                seq=html.escape(row.get("seq") or ""),
                t=html.escape((row.get("wall_time") or "").split(" ")[-1]),
                frame_short=html.escape(Path(frame).name if frame else "-"),
                kind=html.escape(str(facts.get("kind") or row.get("kind") or "-")),
                turn=html.escape(str(facts.get("turn") or "-")),
                dv=html.escape(str(facts.get("dv", ""))),
                facts=html.escape(row.get("facts") or ""),
                line=html.escape(line),
            ))
    out = session_dir / "view.html"
    out.write_text(PAGE.format(title=session_dir.name, rows="\n".join(out_rows)),
                   encoding="utf-8")
    return out


def main(argv):
    if argv == ["--missing"]:
        # view.html이 없는 모든 세션에 생성 — 데모 종료 훅에서 사용.
        made = 0
        for p in sorted(LOG_ROOT.glob("session_*")):
            if p.is_dir() and (p / "log.csv").is_file() \
                    and not (p / "view.html").is_file():
                print(build(p))
                made += 1
        if made == 0:
            print("all sessions already have view.html")
        return
    if not argv or argv == ["--latest"]:
        sessions = sorted(p for p in LOG_ROOT.glob("session_*") if p.is_dir())
        if not sessions:
            raise SystemExit(f"no sessions under {LOG_ROOT}")
        argv = [str(sessions[-1])]
    for arg in argv:
        out = build(Path(arg).expanduser())
        print(out)


if __name__ == "__main__":
    main(sys.argv[1:])
