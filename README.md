# JalSuraksha

Smart Dam Monitoring and Flood Early Warning System for the KRS / Cauvery basin.

## Run locally

1. Install Python 3 on Windows.
2. Double-click `start.bat`.
3. Keep the Python server window open. The staff dashboard opens at `http://127.0.0.1:5000`.
4. Open the farmer and community portal at `http://127.0.0.1:5000/farmer`.

The dashboard uses React, Tailwind, and Leaflet from public CDNs, so an internet connection is needed for those libraries and map tiles.

## Staff sign-in

The staff dashboard requires an admin sign-in. The local `.env` contains `ADMIN_USERNAME` and a generated `ADMIN_PASSWORD`; the default username is `admin`. Keep the password private. Admin sign-in tokens expire after eight hours and are cleared when the server restarts.

The staff API protects farmer details, alert history, dam controls, and alert dispatch. Farmer registrations go through the separate public portal and are saved in `backend/farmers_db.json` for the admin registry.

## Farmer portal

Farmers can view project telemetry at `/farmer` and submit contact, farmland, and location details. The portal requires consent, checks for duplicate email or phone registrations, and uses the same persistent registry as the staff dashboard. Contact details are not verified automatically; staff should confirm them before relying on alerts.

The included telemetry is project/demo data and may be simulated. This project is not an official warning service. Follow instructions from local government and emergency services. The server binds to loopback for local use; public access requires deployment behind HTTPS with suitable production hosting and configuration.

## Configure alert providers

The project reads `.env` from the repository root. Never share it or commit real credentials.

### Email

Configure `SMTP_USER` and `SMTP_PASS` with a Gmail sender account and a newly generated Google App Password. Gmail must have 2-Step Verification enabled. SMTP acceptance does not confirm delivery to the recipient's inbox; check the recipient address and bounce messages.

### SMS

For Indian mobile numbers, set `FAST2SMS_API_KEY` to a Fast2SMS API key and keep `FAST2SMS_ROUTE=q` for Quick SMS. Provider eligibility, required account transactions, charges, message approval, and carrier delivery apply. Alternatively configure all three Twilio values: `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, and `TWILIO_PHONE_NUMBER`.

### WhatsApp

The project opens a prefilled WhatsApp chat. A person must review and tap **Send**; it does not send WhatsApp messages automatically.

## Useful local endpoints

- Staff dashboard: `http://127.0.0.1:5000/`
- Farmer portal: `http://127.0.0.1:5000/farmer`
- Public demo telemetry: `http://127.0.0.1:5000/api/public/dam`
- Staff farmer registry: `http://127.0.0.1:5000/api/farmers` (admin token required)
- Staff alert history: `http://127.0.0.1:5000/api/alerts/history` (admin token required)

## Deploy to Vercel

The repository includes a Vercel Python Function adapter for the current API and rewrites for the staff and farmer pages. Vercel Functions are stateless, so farmer registrations, dam controls, alert history, and admin sign-in sessions use Upstash Redis REST storage when deployed. Without that storage, API requests return a setup error instead of pretending data was saved.

1. Push this repository to GitHub and import it as a Vercel project. Keep the project root set to the repository root.
2. Create an Upstash Redis database and add `UPSTASH_REDIS_REST_URL` and `UPSTASH_REDIS_REST_TOKEN` to Vercel's Production environment variables. Keep the token server-side; never add it to frontend code or commit it.
3. Add `ADMIN_USERNAME` and `ADMIN_PASSWORD` to Vercel's Production environment variables. Use a new, unique admin password for the public deployment.
4. Add `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`, and `SMTP_FROM_NAME` for email. Add `FAST2SMS_API_KEY` and optionally `FAST2SMS_ROUTE`, or all three Twilio variables, for SMS.
5. Redeploy after setting variables. Open `/` for staff and `/farmer` for the community portal. Verify registration, staff login, a single-recipient alert, and the channel delivery results on the deployed URL before relying on it.

All hosted settings belong in Vercel Project Settings → Environment Variables; the local `.env` file is intentionally excluded from Git. The Redis integration stores a shared state document and is suitable for this small project demonstration, not high-volume or concurrent emergency operations. WhatsApp remains click-to-send: an operator must open the chat and tap Send. SMTP acceptance and SMS provider acceptance do not prove final delivery. Telemetry is simulated and is not an official warning service.
