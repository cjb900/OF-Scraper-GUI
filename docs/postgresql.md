[🏠 README](../README.md) · [Install](install.md) · [GUI guide](gui-guide.md) · [Docker](docker.md) · [PostgreSQL](postgresql.md) · [Plugins](plugins.md) · [Versions](versions.md) · [Troubleshooting](troubleshooting.md)

---

# Setting up a PostgreSQL server

OF-Scraper 3.18.0 can keep every creator's records in one PostgreSQL database instead of a `user_data.db` file per creator. It's optional: nothing changes until you turn it on. This page covers **running the server**. What it changes, and how to turn it on in the GUI, are in the [GUI guide](gui-guide.md#postgresql-optional-3180).

You need:

- **PostgreSQL 15 or newer.** The examples use 17.
- **A database and a login that owns it.** The scraper creates its own tables, in one schema per site (`onlyfans`, `fansly`).
- **The driver on the OF-Scraper side.** Since 3.18.1 it's installed with ofscraper on most systems, and the GUI's Docker image has it. Where it's missing, use **Install driver** on the **Manage DBs → PostgreSQL** tab. The standalone `.exe` can't use PostgreSQL.

Pick one way to run the server:

| Option | Use it when |
|---|---|
| [A. Its own `docker-compose.yml`](#a-a-server-in-docker) | You run OF-Scraper on Windows, macOS or Linux (pip, pipx or uv) and have Docker |
| [B. Next to the GUI container](#b-next-to-the-gui-container) | You already run the GUI with this repo's `docker-compose.yml` |
| [C. A server you already have](#c-a-server-you-already-have) | PostgreSQL is already installed, or you'd rather not use Docker |

## A. A server in Docker

1. Make a folder for it, for example `ofscraper-postgres`, with two files.

   `docker-compose.yml`:
   ```yaml
   services:
     postgres:
       image: postgres:17
       container_name: ofscraper-postgres
       restart: unless-stopped
       environment:
         POSTGRES_USER: ofscraper
         POSTGRES_DB: ofscraper
         # read from the .env file next to this one
         POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?set POSTGRES_PASSWORD in .env}
         TZ: UTC
       ports:
         # this computer and your network; use "127.0.0.1:5432:5432"
         # if OF-Scraper runs on this computer only
         - "5432:5432"
       volumes:
         # the database files: keep this folder, back it up with pg_dump (below)
         - ./pgdata:/var/lib/postgresql/data
       healthcheck:
         test: ["CMD-SHELL", "pg_isready -U ofscraper -d ofscraper"]
         interval: 10s
         timeout: 5s
         retries: 5
       shm_size: 256mb
   ```

   `.env`:
   ```text
   POSTGRES_PASSWORD=pick-a-long-password
   ```

2. Start it from that folder:
   ```bash
   docker compose up -d
   docker compose ps
   ```
   After a few seconds `docker compose ps` shows the container as `(healthy)`.

3. In the GUI, open **Manage DBs → PostgreSQL** and enter:

   | Field | Value |
   |---|---|
   | Host | `localhost` when OF-Scraper runs on the same computer; otherwise that computer's IP address, e.g. `192.168.1.20` |
   | Port | `5432` |
   | Database | `ofscraper` |
   | User | `ofscraper` |
   | Password | the one in `.env` |

   Click **Test connection**, then **Save and use PostgreSQL**, then follow the rest of the [GUI guide steps](gui-guide.md#postgresql-optional-3180) (bring your files in, restart).

Notes:

- **The password in `.env` is only used the first time**, when `pgdata` is empty. Changing it later doesn't change the login's password; see [Changing the password](#changing-the-password).
- **Port 5432 already in use** (another PostgreSQL)? Change the left number, e.g. `"5433:5432"`, and use port `5433` in the GUI.
- **Don't forward the port on your router.** The server should only be reachable from your own network.
- **Docker Desktop on Windows:** keep `pgdata` on a Docker volume instead of a Windows folder if the container won't start or is slow. Replace `./pgdata:/var/lib/postgresql/data` with `pgdata:/var/lib/postgresql/data` and add this at the end of the file:
  ```yaml
  volumes:
    pgdata:
  ```

## B. Next to the GUI container

Add the server to this repo's `docker-compose.yml`, under `services:`, beside `ofscraper-gui`:

```yaml
  postgres:
    image: postgres:17
    container_name: ofscraper-postgres
    restart: unless-stopped
    environment:
      POSTGRES_USER: ofscraper
      POSTGRES_DB: ofscraper
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?set POSTGRES_PASSWORD in .env}
      TZ: UTC
    ports:
      # only this host; the GUI container reaches it over host networking
      - "127.0.0.1:5432:5432"
    volumes:
      - /home/YOU/ofscraper-postgres:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ofscraper -d ofscraper"]
      interval: 10s
      timeout: 5s
      retries: 5
    shm_size: 256mb
```

Put `POSTGRES_PASSWORD=...` in a `.env` file next to `docker-compose.yml`, and change `/home/YOU/ofscraper-postgres` to a folder of yours.

So the GUI waits for the server at start-up, add this to the `ofscraper-gui` service:

```yaml
    depends_on:
      postgres:
        condition: service_healthy
```

The host the GUI connects to depends on its networking:

| `ofscraper-gui` networking | Host | Port |
|---|---|---|
| `network_mode: host` (the default, Linux) | `localhost` | `5432` |
| `ports:` block (Docker Desktop) | `postgres` (the service name) | `5432` |

With the `ports:` block, the `ports:` lines on `postgres` aren't needed for the GUI; keep them only if something outside Docker connects too.

Then either:

- enter those details in the GUI under **Manage DBs → PostgreSQL** (as in A, step 3), or
- set the address on `ofscraper-gui` under `environment:`:
  ```yaml
      - OFSC_DATABASE_URL=postgresql://ofscraper:pick-a-long-password@localhost:5432/ofscraper
  ```
  Here a password with `@`, `:`, `/`, `#` or spaces must be percent-encoded (`@` becomes `%40`). The GUI's fields do that for you.

Use one or the other: an address saved in the GUI replaces the one from `environment:`.

Recreate both containers with `docker compose up -d`.

## C. A server you already have

As the `postgres` superuser (`psql -U postgres`), make a login and a database it owns:

```sql
CREATE ROLE ofscraper LOGIN PASSWORD 'pick-a-long-password';
CREATE DATABASE ofscraper OWNER ofscraper;
```

The login must own the database, or at least be allowed to create schemas in it: the scraper creates the `onlyfans` and `fansly` schemas and their tables on first use.

If OF-Scraper runs on another computer, the server must accept connections from it:

- `postgresql.conf`: `listen_addresses = '*'` (or the server's LAN address).
- `pg_hba.conf`: a line for your network, for example `host  ofscraper  ofscraper  192.168.1.0/24  scram-sha-256`.
- Restart PostgreSQL, and allow port 5432 through the server's firewall.

On Windows, PostgreSQL's installer is at [postgresql.org/download/windows](https://www.postgresql.org/download/windows/). Its **pgAdmin** or **SQL Shell (psql)** can run the two commands above.

## Checking it works

After the first scrape with PostgreSQL on, the site's schema and tables are there:

```bash
docker exec -it ofscraper-postgres psql -U ofscraper -d ofscraper -c '\dn'
docker exec -it ofscraper-postgres psql -U ofscraper -d ofscraper -c 'SELECT count(*) FROM onlyfans.medias'
```

(Without Docker: the same `psql -U ofscraper -d ofscraper -c ...` on the server.)

## Backups

There are no automatic backup copies with PostgreSQL (unlike the `user_data.db` backups made before an upgrade). Back it up with `pg_dump`:

```bash
docker exec ofscraper-postgres pg_dump -U ofscraper -Fc ofscraper > ofscraper-$(date +%F).dump
```

Restore into the same database (stop scraping first; this replaces what's there):

```bash
docker exec -i ofscraper-postgres pg_restore -U ofscraper -d ofscraper --clean --if-exists < ofscraper-2026-11-24.dump
```

On Windows PowerShell, `>` and `<` can change the file's bytes. Write the dump inside the container and copy it out instead:

```powershell
docker exec ofscraper-postgres pg_dump -U ofscraper -Fc -f /tmp/ofscraper.dump ofscraper
docker cp ofscraper-postgres:/tmp/ofscraper.dump .\ofscraper.dump
```

## Upgrading PostgreSQL

Minor updates (17.x) only need `docker compose pull` and `docker compose up -d`. A new major version (17 to 18) can't read the old `pgdata` folder. Back up with `pg_dump`, start the new version with an empty folder, then `pg_restore` the dump. PostgreSQL 18's image also stores its data differently: mount the volume at `/var/lib/postgresql` instead of `/var/lib/postgresql/data`.

## Changing the password

```bash
docker exec -it ofscraper-postgres psql -U ofscraper -d ofscraper -c "ALTER ROLE ofscraper PASSWORD 'new-password'"
```

Then update `.env`, and save the new password in the GUI (**Manage DBs → PostgreSQL**, **Save and use PostgreSQL**) or in `OFSC_DATABASE_URL`.

## Troubleshooting

| What you see | What to check |
|---|---|
| Test connection: couldn't connect / connection refused | The container is running and healthy (`docker compose ps`); the host and port are right; the server's firewall allows 5432; with `127.0.0.1:5432:5432`, only that computer can connect |
| Password authentication failed | The password was changed in `.env` after the first start: it only applies to a new, empty `pgdata`. See [Changing the password](#changing-the-password) |
| Database "ofscraper" does not exist | `POSTGRES_DB` was added after the first start, or the name differs. Create it: `docker exec -it ofscraper-postgres createdb -U ofscraper ofscraper` |
| Permission denied for database / schema | The login doesn't own the database. As `postgres`: `ALTER DATABASE ofscraper OWNER TO ofscraper;` |
| The server is PostgreSQL 14 (or older) | Use 15 or newer |
| The container restarts over and over | `docker logs ofscraper-postgres`. "database files are incompatible with server" means `pgdata` is from another major version: see [Upgrading PostgreSQL](#upgrading-postgresql) |
| The driver isn't installed | **Install driver** on the PostgreSQL tab, then restart the GUI |

More about what the scraper does with the database: upstream's [POSTGRESQL.md](https://github.com/datawhores/OF-Scraper/blob/main/POSTGRESQL.md).
