# Running the SPAD GUI on the Windows lab computer — step by step

This guide assumes **zero** technical background. Follow it top to bottom.
You only do Steps 1–2 **once**; after that, starting the program is a single
double-click.

**What you need:** the Windows PC that is connected to the SPAD512² camera,
an internet connection (only for the first run), and about 15 minutes.

---

## Step 1 — Install Python (one time only)

Python is the free program that runs the SPAD bridge.

1. Open your web browser and go to: **https://www.python.org/downloads/**
2. Click the big yellow button that says **"Download Python 3.x.x"**.
3. Open the file it downloaded (bottom of the browser, or in your Downloads
   folder).
4. **IMPORTANT — before clicking anything else:** at the bottom of the
   installer window there is a small checkbox that says
   **"Add python.exe to PATH"**. **Tick it.** This is the one step people
   miss.
5. Now click **"Install Now"** and wait for it to finish. Click **Close**.

*Already installed? Fine — the launcher checks for you and will tell you if
Python is missing or too old (it needs 3.11 or newer).*

## Step 2 — Get the SPAD program (one time only)

No special tools needed — it's a normal ZIP download.

1. Go to: **https://github.com/nirrafa/SPAD512S-remote-gui**
2. Click the green **"<> Code"** button → click **"Download ZIP"**.
3. Go to your Downloads folder, **right-click** the ZIP file →
   **"Extract All..."** → click **Extract**.
4. You now have a folder called something like `SPAD512S-remote-gui-main`.
   **Move it somewhere easy to find** — e.g. drag it onto the Desktop.

## Step 3 — Practice run WITHOUT the camera (recommended)

Before touching the real camera, check that everything works using a built-in
fake camera. Do this while the vendor's Pi Imaging software is **closed**.

1. Open the folder from Step 2, then open the **`launchers`** folder inside it.
2. Double-click **`start-spad-windows-practice.bat`**.
   - If Windows shows *"Windows protected your PC"*: click **"More info"**,
     then **"Run anyway"** (the file is from your own lab's project).
3. A black window opens. **The very first time, it sets itself up — this
   takes a few minutes and needs internet.** Just wait; it tells you what
   it's doing.
4. Your browser opens by itself at `http://localhost:8080`.
   - If the page shows an error, wait 5 seconds and press **F5** (refresh).
5. You should see **"SPAD512² Remote Control"** with **vendor connected** in
   green at the top left. Click **Acquire** on the Intensity tab — a colorful
   noisy image appears. **That's it — everything works.**
6. To stop: close the black window, and also close the small
   **"SPAD fake camera"** window in the taskbar if you see one.

## Step 4 — The real thing

1. Start the vendor's **Pi Imaging SPAD512 software** the way you normally
   do, and make sure the camera is on and connected.
2. In the `launchers` folder, double-click **`start-spad-windows.bat`**
   (the one *without* "practice" in the name).
3. The browser opens. Look at the top left:
   - **"vendor connected"** in green → you're live on the real camera. 🎉
   - **"vendor disconnected"** in red → the vendor software isn't running or
     isn't ready; start it, then wait ~10 seconds (the bridge reconnects by
     itself — no need to restart anything).
4. When you're done: close the black window. That's the off switch.

---

## Step 5 — The smoke test itself

Now walk through this list **in order** and note what happens. Each item says
what to click and what "good" looks like. If something fails, don't fix it —
just **write down exactly what the screen said** (a phone photo is perfect)
and continue to the next item where possible.

| # | What to do | What "good" looks like |
|---|---|---|
| 1 | Just look at the top bar after startup | "vendor connected" green, "idle" shown |
| 2 | **Health** tab | Real temperatures (not 0), laser frequency looks right |
| 3 | **Intensity** tab → Acquire | A real image appears within a few seconds; "saved:" path shown |
| 4 | **Live** tab → Start live | Image refreshes ~3×/second; Stop live halts it |
| 5 | **Gated** tab → Acquire (defaults) | Image + working gate-step slider; drawing a box (rectangle tool) shows a decay curve |
| 6 | **Calibration** tab → run **Noise**, then **Dead pixel** (cap the lens when asked) | Both end "Done"; note how long each takes |
| 7 | **FLIM** tab → Calibrate IRF → Acquire FLIM | Lifetime map + phasor cloud appear |
| 8 | **Intensity** tab → cap the sensor → "Measure dark reference" → uncap → select the reference → Acquire | Green **dark-corrected** badge; image looks cleaner than an uncorrected one |
| 9 | Same as 8 but on the **Gated** tab | Same: badge + cleaner stack; use the **WB sliders** to inspect faint noise |
| 10 | **Gated** tab → set "Cool-off between gate steps" to 5 → Acquire | The run visibly pauses ~5 s between gate steps (watch the step previews arrive slowly); result looks like a normal gated stack |
| 11 | **Intensity** tab → "Add to queue"; **Gated** tab → "Add to queue"; then **Queue** tab → set repeats → Run series | Items run one after another by themselves; status table fills in with "done" + saved paths |
| 12 | **Log** tab | Every run above is listed with its settings (queued runs included) |
| 13 | Find the saved folder (the "saved:" path from item 3) in File Explorer | It contains IMG…png files + `sidecar.json` (+ `meta_*.json` / `movie_arr_*.npy` if "Run reducer" was ticked) |

**If nothing works at all** (item 1 already red): the most useful thing to
check is the vendor software's connection settings — the bridge expects the
vendor's command server on `127.0.0.1`, port `9999`. Take a photo of any
error in the black window.

> For the engineer/AI on the other side: the deeper, ordered validation list
> behind this smoke test is the "Mock vs. real hardware" checklist in
> [constraints.md](constraints.md) (8 items, most-likely-first-failure order).
> Items 1–2 there (`DONE` framing on text responses; the real `R` field
> count) are the ones that would make the whole GUI fail instantly — if the
> smoke test dies at step 1 above, start there.

## Troubleshooting (plain language)

| Problem | Fix |
|---|---|
| Double-click does nothing / window flashes and disappears | Right-click the `.bat` → "Run as administrator" once; if it still flashes, take a photo of it (record your screen with your phone) |
| "Windows protected your PC" | More info → Run anyway |
| A firewall popup appears | Click **Allow access** |
| Browser page says "can't be reached" | Wait 5–10 seconds, press F5 |
| "vendor disconnected" in red | Start the Pi Imaging vendor software; the bridge reconnects on its own within ~10 s |
| "[PROBLEM] Python is not installed" | Do Step 1 — and remember the **PATH checkbox** |
| First-time setup fails | The PC probably has no internet; connect it and double-click again |
| You want to start over completely | Delete the `.venv` folder inside the project folder, double-click again (redoes the few-minute setup) |
