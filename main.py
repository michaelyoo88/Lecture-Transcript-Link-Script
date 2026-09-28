
"""
Panopto transcript helper.

Step 1: Paste a Panopto viewer/embed link then return  a caption (SRT) download link.
        Open that link in logged-in browser to download the .srt file.
Step 2: Give the script the downloaded .srt and a name -> get a clean .txt.
"""

import re
import sys
from pathlib import Path
from urllib.parse import urlparse, parse_qs

GUID_RE = re.compile(r"^[0-9a-fA-F]{8}-([0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}$")


# grabs the school + recording id from your link, spits out the srt link
def build_srt_link(url: str) -> str:
    url = url.strip().strip("'\"")
    parsed = urlparse(url)
    if not parsed.hostname or "panopto" not in parsed.hostname.lower():
        raise ValueError("That doesn't look like a Panopto link.")

    # Query keys can vary in case (id / Id), so normalise them.
    query = {k.lower(): v for k, v in parse_qs(parsed.query).items()}
    rec_id = query.get("id", [""])[0]
    if not GUID_RE.match(rec_id):
        raise ValueError("Couldn't find a valid recording id (id=...) in the link.")

    return (
        f"https://{parsed.hostname}/Panopto/Pages/Transcription/"
        f"GenerateSRT.ashx?id={rec_id}&language=0"
    )


# strips numbers/timestamps so it's just the words
def srt_to_text(raw: str) -> str:
    raw = raw.lstrip("\ufeff")
    raw = re.sub(r"^WEBVTT.*$", "", raw, flags=re.M)
    raw = re.sub(r"^\d+\s*$", "", raw, flags=re.M)
    raw = re.sub(r"^\d{1,2}:\d\d(:\d\d)?[.,]\d+\s*-->.*$", "", raw, flags=re.M)
    raw = re.sub(r"<[^>]+>", "", raw)  # stray tags like <i>

    lines, prev = [], None
    for line in (l.strip() for l in raw.splitlines()):
        if line and line != prev:  # skip blanks and immediate repeats
            lines.append(line)
        prev = line
    return "\n".join(lines)


# fixes weird paths from dragging a file into the terminal
def clean_path(p: str) -> Path:
    p = p.strip().strip("'\"").replace("\\ ", " ")
    return Path(p).expanduser()


# removes characters that break filenames
def safe_filename(name: str) -> str:
    name = re.sub(r'[\\/:*?"<>|]', "_", name.strip())
    return name or "transcript"


# finds newest .srt in Downloads so you don't have to type the path
def latest_srt_in_downloads():
    downloads = Path.home() / "Downloads"
    files = sorted(downloads.glob("*.srt"), key=lambda f: f.stat().st_mtime, reverse=True)
    return files[0] if files else None


# runs the whole flow: link -> download -> txt
def main():
    # ---- Step 1: build the link ----
    link_in = input("Paste the Panopto link: ")
    try:
        srt_link = build_srt_link(link_in)
    except ValueError as e:
        sys.exit(f"Error: {e}")

    print("\nPaste this into your browser (while logged in) to download the .srt:\n")
    print(srt_link)

    # ---- Step 2: convert to txt ----
    print("\nOnce it's downloaded, we can turn it into a clean .txt file.")
    if input("Convert now? [Y/n]: ").strip().lower() == "n":
        return

    name = safe_filename(input("Name for the transcript (e.g. Lecture 10): "))

    default = latest_srt_in_downloads()
    prompt = "Path to the downloaded .srt (drag the file here"
    prompt += f", or press Enter for {default.name}): " if default else "): "
    entered = input(prompt).strip()
    srt_path = clean_path(entered) if entered else default

    if not srt_path or not srt_path.is_file():
        sys.exit("Couldn't find that file.")

    text = srt_to_text(srt_path.read_text(encoding="utf-8", errors="replace"))
    if not text:
        sys.exit("The file was empty. Captions may be disabled or not generated yet.")

    out = Path.cwd() / f"{name}.txt"
    out.write_text(text, encoding="utf-8")
    print(f"\nSaved: {out}")


if __name__ == "__main__":
    main()