# Connecting PARKER to Google Calendar

A one-time setup, about 10–15 minutes, free. Google requires every app that reads a calendar,
even a personal one, to be registered. You register PARKER in your own Google Cloud account,
so no one else is involved and nothing is shared.

**What PARKER gets:** permission to read and add **events** (`calendar.events`). Not your
calendar settings, not sharing, not Gmail. PARKER always shows an event and asks before adding
it. Remove access any time at <https://myaccount.google.com/permissions>.

**Where the keys live:** `memory/credentials.json` and `memory/google_token.json`, on your laptop
only. Git ignores both (and the whole `memory/` folder), so they can never be pushed to GitHub.

> Google renames its console menus from time to time. If a name below doesn't match exactly,
> look for the closest one; the steps are the same.

## 1. Create a project

1. Go to <https://console.cloud.google.com/> and sign in with the Google account whose calendar
   you want PARKER to use.
2. Click the project picker at the top → **New project** → name it `PARKER` → **Create**.
3. Make sure `PARKER` is selected in the project picker.

## 2. Turn on the Calendar API

1. Menu → **APIs & Services** → **Library**.
2. Search for **Google Calendar API** → open it → **Enable**.

## 3. Set up the sign-in screen

1. Menu → **Google Auth Platform** (older name: **APIs & Services → OAuth consent screen**) →
   **Get started**.
2. **App name:** `PARKER`. **User support email:** your email.
3. **Audience:** **External**.
4. **Contact information:** your email. Agree to the policy → **Create**.
5. Open **Audience** → **Test users** → **Add users** → add **your own Gmail address** → **Save**.

## 4. Create PARKER's key

1. In Google Auth Platform → **Clients** (older: **APIs & Services → Credentials → Create
   credentials → OAuth client ID**) → **Create client**.
2. **Application type:** **Desktop app**. **Name:** `PARKER` → **Create**.
3. Click **Download JSON**.
4. Move the downloaded file into your PARKER folder as **`memory\credentials.json`**:

   ```powershell
   mkdir memory -Force
   Move-Item "$HOME\Downloads\client_secret_*.json" memory\credentials.json
   ```

## 5. Connect

```powershell
python -m pip install -r requirements.txt
python -m backend.calendar_connect
```

A browser tab opens on Google's own page:

1. Choose your account.
2. You'll see **"Google hasn't verified this app"**. That's expected: it's your own app, made
   minutes ago. Click **Advanced** → **Go to PARKER (unsafe)**.
3. Allow **"See, edit, share, and permanently delete all the calendars you can access…"**. (This
   is Google's standard wording for the events permission. PARKER only lists and adds events,
   and only after asking you.)
4. The tab says the flow is complete. Back in PowerShell, PARKER lists your next 7 days.

Then restart PARKER (`python -m frontend.app`). The greeting and the Agenda drawer now include
your Google events, and you can say "add a meeting with Rahul to my calendar tomorrow at 3".

## If PARKER asks you to reconnect every week

While the app is in **Testing**, Google lets its sign-in last about 7 days. To stop that, open
**Google Auth Platform → Audience → Publish app**. It stays unverified (fine for personal use; you
just see the warning in step 5 again once), and the sign-in then lasts until you remove it.

## Troubleshooting

| Message | Fix |
|---|---|
| `Put the OAuth client file … at memory\credentials.json` | Step 4 |
| `Google Calendar isn't connected yet` | Step 5 |
| `Google sign-in expired` | Run `python -m backend.calendar_connect` again (see the weekly note above) |
| `access_denied` in the browser | Add your Gmail address as a test user (step 3.5) |
| `Google Calendar API has not been used in project …` | Enable the API (step 2), wait a minute, retry |
