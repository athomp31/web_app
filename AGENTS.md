# Project file layout

Keep the web app in the project root as `web_app.html`. The root `index.html`
is a redirect to `web_app.html` so GitHub Pages can continue serving the app
from the default directory URL. The root also contains `spec.md` for the
project specification and `prompts.md` for prompts, along with this
`AGENTS.md`.

Save new files in the folder that matches their purpose:

- `00_planning/` — planning notes and sketches.
- `01_data/` — data files.
- `02_validation/` — hand calculations and test cases.
- `03_output/` — screenshots and exported results.

Each numbered folder has a `README.md` describing what belongs there. Keep
application code in the top-level `web_app.html`; do not move it into a
numbered folder.