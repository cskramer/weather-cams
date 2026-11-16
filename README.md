# weather-cams

Shared place list and webcam feeds for the ESP32 weather stations. One file, `config/cams.json`, is the single place to fix a camera; every device reads it from GitHub. A scheduled GitHub Actions job turns each camera (still image, video stream or YouTube) into a plain JPEG on the `cams` branch.

## Setup
1. Create a **public** repo called `weather-cams` and push this folder to it (public keeps scheduled runs free and the picture links simple).
2. Repo **Settings -> Actions -> General -> Workflow permissions -> Read and write**.
3. **Actions** tab -> **Mirror cameras** -> **Run workflow**. It then runs every 5 minutes (GitHub may be a few minutes late).
4. Open the finished run: the log shows `ok` or `FAIL` with the reason for each camera. The `cams` branch gets one JPEG per place plus `status.json`.
5. In each device's firmware set `CAMS_REPO` to `your-user/weather-cams`.

## The config file
Groups: `fam`, `fav`, `ski`, `other` (menu order = file order). Each place:

    {"id":"pikes-peak","name":"Pikes Peak","country":"USA","lat":38.8405,"lon":-105.0443,
     "elev":4302,"radius":0.05,
     "sources":[{"type":"still","url":"https://.../image.jpg"}]}

`sources` are tried in order; the first that works wins.
- `still`: a direct picture address (jpg, png, webp).
- `hls`: a video stream address (`.m3u8` etc.); one frame is grabbed with ffmpeg.
- `youtube`: a watch or live address (yt-dlp).
- `page`: any web page, opened in a headless browser and screenshotted after `wait` seconds (default 10); optional `selector` (e.g. `"video"`) shoots just that element. For players that only work inside a page (Verkada, HD Relay, YouTube embeds). Slower than the others, so put it after cheaper sources.
Optional on a source: `referer`, and `"insecure": true` (skip certificate checking, for cameras whose HTTPS certificate is broken). Optional on a place: `note`, `elev` (meters, `null` for terrain default), `radius` (degrees, about 111 km each: how close a searched city must be to use this camera). Max 24 places per group. Entries marked `"unverified": true` are guesses; check the run log.

Edit it right on GitHub. Devices pick up changes within 6 hours, or immediately when REFRESH is pressed on the home screen. Output pictures are baseline JPEGs of at most 1280 pixels; if every source fails the last good picture is kept for 24 hours, then removed so devices fall back to the camera's own address.

To find a stream address: open the camera page, press F12, **Network** tab, filter `m3u8` (or look for a `.jpg` that changes), copy the link.

## Honest limits
- Some sites block GitHub's datacenter addresses (YouTube often does), and many stream addresses expire or refuse other sites. Put a plain `still` source last as a fallback.
- Some sites don't allow automatic downloading; check their terms.
- GitHub can disable scheduled workflows after about 60 days without activity; re-enable under the Actions tab if pictures go stale.
- Cloudcroft has no feed yet.

## Testing locally
    pip install -r tools/requirements.txt
    python tools/mirror_cams.py config/cams.json out

(needs ffmpeg for video sources.)
