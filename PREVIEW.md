# Local UI preview

Double-click **Start-Preview.cmd**. It opens http://127.0.0.1:8770 in your browser.
Keep the console open while browsing; close it or press Ctrl+C to stop.

The preview needs Python 3.10+ only. The downloadable/local ZIP includes the compiled dashboard, so Node.js, Google credentials and backend dependencies are unnecessary.

This is explicitly **sample data**, separate from the real archive database. Explore all eight pages, dark/light mode, responsive layouts, queue buttons and metadata editing. Edits last until the preview process stops. Folder access, Google authorization, real file transfers and uploads are disabled. Queue controls change sample state only.

If running from a fresh source checkout rather than the preview ZIP, first run `npm ci` and `npm run build` inside `frontend` to generate the dashboard. Then use the launcher above.

If port 8770 is already used, run `python scripts/preview.py --port 8771`.

For the full archiving application, follow **SETUP_WINDOWS.md** instead.
