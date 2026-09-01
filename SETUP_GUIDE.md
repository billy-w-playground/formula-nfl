# Dummy Guide: Getting the App Running (Mac, zero experience assumed)

Two paths. **Path B (cloud) needs no installs at all** and gets you a real
hosted app like your friend's — recommended for you. Path A runs it on your
laptop.

---

## Path B — Streamlit Community Cloud (no Python install, ~15 min)

1. **Make a GitHub account** at github.com (free).
2. **Create a repository**: click the "+" (top right) → *New repository* →
   name it `walters-nfl-model` → keep it **Public** → *Create repository*.
3. **Upload the files**: on the new repo page click *uploading an existing
   file*. Unzip `walters_app.zip` on your Mac first (double-click it), then
   drag EVERYTHING inside the `walters_app` folder into the browser window —
   `app.py`, `requirements.txt`, `README.md`, and the whole `walters` folder.
   (Drag the `walters` folder itself; GitHub keeps the structure.) Click
   *Commit changes*.
4. **Deploy**: go to share.streamlit.io → sign in with GitHub → *Create app*
   → pick your repo → main file path = `app.py` → *Deploy*.
5. Two minutes later you have a URL like `walters-nfl-model.streamlit.app`
   that works on your phone. Every time you edit a file on GitHub, the app
   redeploys itself.
6. **Odds API key** (optional): in the app's Streamlit settings → *Secrets*
   is the proper place, but for now just paste it in the sidebar each run.

## Path A — Run locally on your Mac (~20 min first time)

1. **Install Python**: go to python.org/downloads → big yellow button →
   open the downloaded .pkg → click through the installer. This gives you
   `python3` and `pip3`.
2. **Open Terminal** (Cmd+Space, type "Terminal", Enter).
3. **Go to the folder**: type `cd ` (with a trailing space), then drag the
   unzipped `walters_app` folder from Finder onto the Terminal window, and
   press Enter.
4. **Install the libraries** (one time):
   `pip3 install -r requirements.txt`
5. **Run it**:
   `streamlit run app.py`
   Your browser opens to `localhost:8501`. Leave Terminal open while using it.
6. **To stop**: Ctrl+C in Terminal. To run again later: repeat steps 2-3-5.

If step 5 says `command not found: streamlit`, run
`python3 -m streamlit run app.py` instead.
