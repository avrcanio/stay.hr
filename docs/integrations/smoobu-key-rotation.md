# Smoobu API key rotation (uzorita)

Production Booking.com listings for Uzorita use **Smoobu** as the channel manager. API credentials live only in **encrypted** `IntegrationConfig` (`provider=smoobu`), never in git or chat.

## Rotate after exposure

1. In [Smoobu](https://login.smoobu.com) → **Advanced** → **API Keys**, **revoke** the compromised key and **generate** a new one.
2. On the server, set the new key only in `.env` (not committed):

   ```bash
   # .env
   SMOOBU_API_KEY=<new-key>
   ```

3. Apply migration if needed, then seed or rotate:

   ```bash
   cd /opt/stacks/stay.hr
   docker compose exec django python manage.py migrate integrations
   docker compose exec django python manage.py seed_uzorita_smoobu_config
   ```

   To update an existing config without changing apartment mapping:

   ```bash
   docker compose exec django python manage.py rotate_smoobu_api_key
   ```

4. Confirm: command prints Smoobu user id/email from `GET /api/me`; `IntegrationConfig.config` column stays `{}` and `config_encrypted` is populated.

## Channel policy

Do **not** push ARI to Channex for the same live units (R1–R6) while Smoobu is active. Channex remains for cert/demo property only.
