#!/usr/bin/env python3
"""Turn every camera source in config/cams.json into one baseline JPEG per place.

For each place the sources are tried in order and the first one that produces a
valid picture wins. A place whose sources all fail keeps its previous picture
(until it is more than MAX_AGE_H old, then the file is removed so devices fall
back to the camera's own address). Writes <out>/<id>.jpg and <out>/status.json.

usage: mirror_cams.py CONFIG OUT_DIR
"""
import io, json, os, shutil, subprocess, sys, tempfile, time
import requests
from PIL import Image, ImageStat

MAX_AGE_H = 24
MAX_SIDE = 1280          # downscale only; the device resizes to 800x480 itself
MAX_BYTES = 600_000      # the device buffer is 900 KB, stay well under
MIN_W, MIN_H = 320, 180
UA = "Mozilla/5.0 (X11; Linux x86_64) weather-cam-mirror"
HTTP_TIMEOUT = 20
VIDEO_TIMEOUT = 45


def to_jpeg(raw: bytes) -> bytes:
    """Decode any picture Pillow knows (jpg/png/webp) and re-encode as baseline JPEG."""
    im = Image.open(io.BytesIO(raw))
    im.load()
    im = im.convert("RGB")
    if im.width < MIN_W or im.height < MIN_H:
        raise ValueError(f"picture too small ({im.width}x{im.height})")
    if max(im.size) > MAX_SIDE:
        s = MAX_SIDE / max(im.size)
        im = im.resize((round(im.width * s), round(im.height * s)), Image.LANCZOS)
    if max(ImageStat.Stat(im.convert("L")).extrema[0][1], 0) < 4:
        raise ValueError("picture is completely black")
    for q in (88, 80, 70, 60):
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=q, progressive=False, optimize=False)
        if buf.tell() <= MAX_BYTES:
            return buf.getvalue()
    raise ValueError("picture too large even at low quality")


def grab_still(src):
    h = {"User-Agent": UA}
    if src.get("referer"):
        h["Referer"] = src["referer"]
    r = requests.get(src["url"], headers=h, timeout=HTTP_TIMEOUT)
    r.raise_for_status()
    return to_jpeg(r.content)


def ffmpeg_frame(url, referer=None):
    with tempfile.TemporaryDirectory() as d:
        out = os.path.join(d, "f.jpg")
        cmd = ["ffmpeg", "-y", "-loglevel", "error"]
        if url.startswith("http"):          # http-only options
            cmd += ["-user_agent", UA]
            if referer:
                cmd += ["-headers", f"Referer: {referer}\r\n"]
        cmd += ["-i", url, "-frames:v", "1", "-q:v", "3", out]
        subprocess.run(cmd, check=True, timeout=VIDEO_TIMEOUT, capture_output=True)
        with open(out, "rb") as f:
            return to_jpeg(f.read())


def grab_hls(src):
    return ffmpeg_frame(src["url"], src.get("referer"))


def grab_youtube(src):
    r = subprocess.run(
        ["yt-dlp", "-g", "-f", "best[height<=720]/best", "--no-warnings", src["url"]],
        check=True, timeout=VIDEO_TIMEOUT, capture_output=True, text=True)
    lines = [l for l in r.stdout.splitlines() if l.strip()]
    if not lines:
        raise ValueError("yt-dlp returned no stream address")
    return ffmpeg_frame(lines[0])


GRABBERS = {"still": grab_still, "hls": grab_hls, "youtube": grab_youtube}


def main(cfg_path, out_dir):
    cfg = json.load(open(cfg_path))
    os.makedirs(out_dir, exist_ok=True)
    status_path = os.path.join(out_dir, "status.json")
    try:
        old = json.load(open(status_path))
    except Exception:
        old = {}
    now = int(time.time())
    status, ok_n, total = {}, 0, 0
    for group, places in cfg["groups"].items():
        for p in places:
            pid, srcs = p["id"], p.get("sources", [])
            if not srcs:
                continue
            total += 1
            jpg_path = os.path.join(out_dir, pid + ".jpg")
            errors, used = [], None
            for i, src in enumerate(srcs):
                t = src.get("type", "still")
                try:
                    data = GRABBERS[t](src)
                    tmp = jpg_path + ".tmp"
                    with open(tmp, "wb") as f:
                        f.write(data)
                    os.replace(tmp, jpg_path)
                    used = i
                    status[pid] = {"ok": True, "source": i, "type": t, "bytes": len(data), "last_ok": now}
                    break
                except Exception as e:  # keep going: next source
                    msg = getattr(e, "stderr", None)
                    if isinstance(msg, bytes):
                        msg = msg.decode(errors="replace")
                    errors.append(f"source {i} ({t}): {type(e).__name__}: {(msg or str(e))[:160]}".strip())
            if used is None:
                prev = old.get(pid, {})
                last_ok = prev.get("last_ok", 0)
                stale = (now - last_ok) > MAX_AGE_H * 3600
                if stale and os.path.exists(jpg_path):
                    os.remove(jpg_path)
                status[pid] = {"ok": False, "last_ok": last_ok, "errors": errors,
                               "removed_stale": bool(stale)}
                print(f"FAIL {pid}: " + " | ".join(errors))
            else:
                ok_n += 1
                print(f"ok   {pid}: source {used} ({status[pid]['type']}), {status[pid]['bytes']} bytes")
    status["_run"] = {"time": now, "ok": ok_n, "total": total}
    with open(status_path, "w") as f:
        json.dump(status, f, indent=1)
    print(f"{ok_n}/{total} cameras updated")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    sys.exit(main(sys.argv[1], sys.argv[2]))
