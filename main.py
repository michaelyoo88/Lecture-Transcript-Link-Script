
"""
Panopto transcript helper.

Step 1: Paste a Panopto viewer/embed link then return a caption download link.
        Open that link in logged-in browser to download the captions .txt file.
Step 2: Give the script the downloaded captions .txt and a name -> get a clean
        block of text.
"""

import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse, parse_qs

GUID_RE = re.compile(r"^[0-9a-fA-F]{8}-([0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}$")
PARAGRAPH_CHARS = 600  # start a new paragraph after the sentence that passes this length



# grabs the school + recording id from your link, spits out the txt link
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
        f"GenerateSRT.ashx?id={rec_id}&language=0\n"
    )


# strips numbers/timestamps/banners and joins captions into readable paragraphs
def captions_to_text(raw: str) -> str:
    raw = raw.lstrip("\ufeff")
    raw = re.sub(r"^WEBVTT.*$", "", raw, flags=re.M)
    raw = re.sub(r"^\d+\s*$", "", raw, flags=re.M)
    raw = re.sub(r"^\d{1,2}:\d\d(:\d\d)?[.,]\d+\s*-->.*$", "", raw, flags=re.M)
    raw = re.sub(r"<[^>]+>", "", raw)  # stray tags like <i>
    raw = re.sub(r"^\[Auto-generated transcript.*\]\s*$", "", raw, flags=re.M)

    lines, prev = [], None
    for line in (l.strip() for l in raw.splitlines()):
        if line and line != prev:  # skip blanks and immediate repeats
            lines.append(line)
        prev = line
    return to_paragraphs(re.sub(r"\s+", " ", " ".join(lines)).strip())


# groups sentences into ~PARAGRAPH_CHARS paragraphs, only breaking after a full sentence
def to_paragraphs(text: str) -> str:
    # split after . ! ? when the next word starts a new sentence (capital/quote/digit)
    sentences = re.split(r"(?<=[.!?])\s+(?=[\"'A-Z0-9])", text)
    paragraphs, current = [], ""
    for sentence in sentences:
        current = f"{current} {sentence}" if current else sentence
        if len(current) >= PARAGRAPH_CHARS:
            paragraphs.append(current)
            current = ""
    if current:
        paragraphs.append(current)
    return "\n\n".join(paragraphs)


# fixes weird paths from dragging a file into the terminal
def clean_path(p: str) -> Path:
    p = p.strip().strip("'\"").replace("\\ ", " ")
    return Path(p).expanduser()


# removes characters that break filenames
def safe_filename(name: str) -> str:
    name = re.sub(r'[\\/:*?"<>|]', "_", name.strip())
    return name or "transcript"


# finds newest Panopto captions .txt in Downloads so you don't have to type the path
def latest_captions_in_downloads():
    downloads = Path.home() / "Downloads"
    files = sorted(downloads.glob("*_Captions_*.txt"), key=lambda f: f.stat().st_mtime, reverse=True)
    return files[0] if files else None


# reads the link from the clipboard. Pasting into input() hangs because macOS
# terminals cap a typed line at 1024 chars and Panopto links (with their
# lti_stored_token) are longer than that.
def read_clipboard_link() -> str:
    input("Copy the Panopto link, then press Enter (don't paste it here): ")
    try:
        return subprocess.run(["pbpaste"], capture_output=True, text=True).stdout
    except FileNotFoundError:
        sys.exit("Clipboard not available. Pass the link as an argument instead:\n"
                 "  python3 main.py '<link>'")


# keeps asking until we get a valid Panopto link (argv is tried first, once)
def get_srt_link() -> str:
    link_in = sys.argv[1] if len(sys.argv) > 1 else read_clipboard_link()
    while True:
        try:
            return build_srt_link(link_in)
        except ValueError as e:
            print(f"Error: {e} Try again (Ctrl+C to quit).\n")
        link_in = read_clipboard_link()


# keeps asking until we get a captions file that has text in it
def get_captions() -> tuple[Path, str]:
    while True:
        default = latest_captions_in_downloads()
        prompt = "Choose desired Panopto captions .txt file: \n"
        prompt += f"1) Press Enter for {default.name}): " if default else "): "
        prompt += "\n OR \n"
        prompt += "2) Drag the desired downloaded txt file here: "
        entered = input(prompt).strip()
        captions_path = clean_path(entered) if entered else default

        if not captions_path or not captions_path.is_file():
            print("Couldn't find that file. Try again (Ctrl+C to quit).\n")
            continue

        text = captions_to_text(captions_path.read_text(encoding="utf-8", errors="replace"))
        if not text:
            print("The file was empty. Captions may be disabled or not generated yet. "
                  "Try again (Ctrl+C to quit).\n")
            continue
        return captions_path, text


# runs the whole flow: link -> download -> txt
def main():
    # ---- Step 1: build the link ----
    srt_link = get_srt_link()

    print("\nPaste this into your browser (while logged in) to download the captions .txt:\n")
    print(srt_link)



    captions_path, text = get_captions()

    # "Lecture 3 BIOL1100 26_Captions_English (United States)" -> "Lecture 3 BIOL1100 26"
    suggested = captions_path.stem.split("_Captions_")[0]
    name = safe_filename(input(f"Name for the transcript (press Enter for {suggested}): ") or suggested)

    out = Path.home() / "Downloads" / f"{name}.txt"
    if out.resolve() == captions_path.resolve():
        out = out.with_name(f"{name} (clean).txt")  # don't overwrite the source
    out.write_text(text + "\n", encoding="utf-8")
    print(f"\nSaved: {out}")


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        print("\nCancelled.")
