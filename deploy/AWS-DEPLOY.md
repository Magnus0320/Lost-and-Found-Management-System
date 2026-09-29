# Deploying Campus Lost & Found to AWS

Written for someone who has not used AWS before. Every step says what you are
doing and why, so you can explain the result rather than just having clicked
through it.

**The shape of it.** One small Linux server (an EC2 instance) runs the three
containers you already run locally: the API, PostgreSQL, and a new reverse
proxy called Caddy that handles HTTPS. There is no managed database, no load
balancer, and no container service, because each of those costs real money and
none of them is needed for a demo.

```
internet ──► EC2 instance ─┬─ caddy    :80/:443   TLS, the only thing exposed
                           ├─ api      :8000      FastAPI + the UI at /app/
                           └─ db       :5432      PostgreSQL, private
```

---

## Before you touch AWS

### Push your code. This is not optional.

Your local working copy has an entire feature that has **never been committed**
— the admin panel. These files exist on your Mac and nowhere else:

```
app/routers/admin.py              frontend/admin.html
app/schemas/admin.py              frontend/js/pages/admin.js
app/services/admin_service.py     scripts/make_admin.py
migrations/versions/b052f2f503ff_add_is_admin_flag_to_users.py
tests/test_admin.py               tests/test_contact_disclosure.py
```

Plus roughly twenty modified files. The server builds from GitHub, so if you
deploy now you get a site with **no admin panel and no `is_admin` column**,
while your README advertises both. Commit and push first:

```bash
git add -A
git commit -m "Add admin panel, contact disclosure, and AWS deployment config"
git push origin main
```

Check `git status` afterwards — it should say "nothing to commit, working tree
clean." Your `.env` is gitignored and will not be pushed; that is correct.

### Know which AWS account you have

This matters more than anything else in this document.

| | AWS Academy Learner Lab | Normal account |
|---|---|---|
| How you get in | Canvas course, "Start Lab" button | `aws.amazon.com` sign-in |
| Session | Ends after ~4 hours | Never |
| Your instance | **Stopped when the session ends** | Runs until you stop it |
| Public IP | **Changes on every restart** | Can be fixed with an Elastic IP |
| Good for | Learning, screenshots, a live walkthrough | A permanent portfolio link |

If you are on a Learner Lab, a permanently reachable URL is not achievable —
that is a property of the lab, not something to work around. Read the
[Learner Lab section](#if-you-are-on-an-aws-academy-learner-lab) at the end.

### What this will cost

| Item | Legacy free tier | Credits-model account |
|---|---|---|
| t3.micro instance | Free (750 h/month) | ~$7.60/month |
| 30 GB disk | Free | ~$2.40/month |
| Public IPv4 address | Free (750 h/month) | ~$3.60/month |
| **Total** | **$0** | **~$13.60/month** |

The split is the July 2025 change. Accounts opened **before** roughly July 15,
2025 have the old 12-month free tier, where the above is genuinely $0. Accounts
opened **after** get credits instead ($100 at signup, up to $200 total, expiring
after 12 months) and then pay normal rates. On the credits model, ~$100 buys
this stack about seven months.

Two things to note regardless: a public IPv4 address is **no longer free by
default** — that changed in February 2024 — and on the new "Free Plan" the
account **auto-closes** when credits run out, with 90 days to retrieve data.

---

## Step 1 — Set a billing alarm before anything else

Do this first, every time, on any cloud account. It is the difference between a
surprise and a notification.

1. Sign in, click your **account name, top right** → **Billing and Cost
   Management**.
2. Left sidebar → **Billing preferences** → tick **Receive AWS Free Tier alerts**
   and enter your email → **Save**.
3. Left sidebar → **Budgets** → **Create budget** → choose **Zero spend budget**
   (a preset that alerts on the first cent) or **Monthly cost budget** with a $5
   limit → enter your email → **Create**.

Budgets are free and evaluate a few times a day.

## Step 2 — Get a free hostname

You need a hostname, not just an IP address, for two reasons: Let's Encrypt will
not issue a certificate for a bare IP, and without HTTPS your login page sends
passwords in clear text. A free subdomain solves both.

1. Go to **https://www.duckdns.org** and sign in with GitHub or Google.
2. Type a subdomain — say `campus-lostfound` — and click **add domain**.
3. You now own `campus-lostfound.duckdns.org`. Leave the tab open; you will
   paste your server's IP into the **current ip** box in Step 6.

DuckDNS is free, permanent, and lets you repoint the name whenever the IP
changes — which is exactly what you need on a Learner Lab.

## Step 3 — Create a key pair

This is the SSH key you use to log into the server. AWS generates it and lets
you download the private half exactly once.

1. Console search bar → **EC2** → left sidebar **Key Pairs** → **Create key pair**.
2. Name: `lostfound-key`. Type: **RSA**. Format: **.pem**.
3. **Create key pair.** The file downloads automatically. Then lock it down —
   SSH refuses to use a key that other users can read:

```bash
mkdir -p ~/.ssh && mv ~/Downloads/lostfound-key.pem ~/.ssh/
chmod 400 ~/.ssh/lostfound-key.pem
```

Lose this file and you lose access to the server. There is no recovery.

## Step 4 — Create a security group

A security group is a firewall. The default blocks everything inbound, and you
open only what you need.

1. EC2 sidebar → **Security Groups** → **Create security group**.
2. Name `lostfound-sg`, description `Web and SSH for lost and found`.
3. Add three **inbound** rules:

| Type | Port | Source | Why |
|---|---|---|---|
| SSH | 22 | **My IP** | Administration. Never `0.0.0.0/0`. |
| HTTP | 80 | Anywhere IPv4 | Visitors, and Let's Encrypt's domain check. |
| HTTPS | 443 | Anywhere IPv4 | Visitors. |

4. Leave outbound alone (allow all — the server needs to fetch packages).
5. **Create security group.**

Note what is *not* here: port 5432. Your development `docker-compose.yml`
publishes PostgreSQL to the host, which on a public server would expose your
database to the internet. `docker-compose.prod.yml` removes that mapping, and
this security group is the second lock on the same door.

## Step 5 — Launch the instance

1. EC2 → **Instances** → **Launch instances**.
2. **Name**: `lostfound-server`.
3. **AMI**: Ubuntu Server 24.04 LTS. Confirm it says *Free tier eligible*.
4. **Instance type**: `t3.micro` (or `t2.micro` if t3 is not marked free-tier
   eligible in your region).
5. **Key pair**: `lostfound-key`.
6. **Network settings** → **Select existing security group** → `lostfound-sg`.
7. **Storage**: 30 GiB gp3. This is the free-tier maximum; the default 8 GiB
   fills up with Docker images.
8. **Advanced details** → scroll to the bottom → **User data**. Paste the entire
   contents of `deploy/bootstrap-ec2.sh`, **after editing the three variables at
   the top**:

```bash
REPO_URL="https://github.com/Magnus0320/Lost-and-Found-Management-System.git"
REPO_BRANCH="main"
SITE_ADDRESS=""            # leave EMPTY for now -- DNS does not point here yet
ACME_EMAIL="you@example.com"
```

   `SITE_ADDRESS` stays empty on this first boot deliberately. Caddy would try
   to get a certificate immediately, Let's Encrypt would fail to verify a
   hostname that does not yet resolve to this server, and repeated failures
   count against a rate limit. You will fill it in at Step 7.

9. **Launch instance.**

The bootstrap script installs Docker, adds swap (the 1 GiB of RAM on a
free-tier box is not enough to build the Python image — without swap the build
is silently killed), clones your repo, generates a random `SECRET_KEY` and
database password, and starts the stack. Expect 5–10 minutes.

## Step 6 — Point the hostname at the server

1. EC2 → **Instances** → select yours → copy the **Public IPv4 address**.
2. Back on DuckDNS, paste it into **current ip** → **update ip**.
3. Confirm it resolves:

```bash
dig +short campus-lostfound.duckdns.org
```

4. Meanwhile, watch the bootstrap finish:

```bash
ssh -i ~/.ssh/lostfound-key.pem ubuntu@<PUBLIC_IP>
sudo tail -f /var/log/cloud-init-output.log
```

   Wait for `=== [bootstrap] Bootstrap finished ===`. Then:

```bash
curl http://localhost/health
# {"status":"ok","database":"reachable","version":"1.0.0"}
```

The site is now live over plain HTTP at `http://<PUBLIC_IP>/app/`. Do not
create a real account yet — that password would cross the internet unencrypted.

## Step 7 — Turn on HTTPS

Now that DNS resolves, let Caddy get a certificate.

```bash
cd /opt/lostfound
sudo sed -i 's|^SITE_ADDRESS=.*|SITE_ADDRESS=campus-lostfound.duckdns.org|' .env.prod
sudo docker compose -f docker-compose.prod.yml --env-file .env.prod up -d
sudo docker compose -f docker-compose.prod.yml --env-file .env.prod logs -f caddy
```

Look for `certificate obtained successfully`. It takes 10–30 seconds. Caddy
renews automatically from here; there is nothing to schedule.

Visit **https://campus-lostfound.duckdns.org** — you should get the UI with a
padlock, and `http://` should redirect to `https://` on its own.

## Step 8 — Make yourself an admin

`/admin/users/{id}/role` requires an admin to call it, so the first one has to
be created directly on the server.

1. Register normally through the UI. With `MAIL_ENABLED=false` the API hands
   back the one-time code as `otp_debug` in the response, so you can verify the
   account without any mail server.
2. Then, over SSH:

```bash
cd /opt/lostfound
sudo docker compose -f docker-compose.prod.yml --env-file .env.prod \
  exec api python scripts/make_admin.py you@example.com
```

3. Confirm, then reload the UI — `/app/admin.html` is now reachable.

```bash
sudo docker compose -f docker-compose.prod.yml --env-file .env.prod \
  exec api python scripts/make_admin.py --list
```

## Step 9 — Check it properly

```bash
curl -s https://campus-lostfound.duckdns.org/health
curl -s -o /dev/null -w '%{http_code}\n' https://campus-lostfound.duckdns.org/docs
curl -s -o /dev/null -w '%{redirect_url}\n' http://campus-lostfound.duckdns.org/
```

Expect the health JSON, `200`, and a redirect to the HTTPS URL. Then, in a
browser: register, log in, report an item, search for it, file a claim, approve
it, and confirm the contact email appears only after approval.

---

## Running it day to day

All from `/opt/lostfound`. The commands are long; make them short once:

```bash
echo "alias lf='sudo docker compose -f /opt/lostfound/docker-compose.prod.yml --env-file /opt/lostfound/.env.prod'" >> ~/.bashrc
source ~/.bashrc
```

| Task | Command |
|---|---|
| Status | `lf ps` |
| Logs | `lf logs -f api` |
| Restart | `lf restart api` |
| Deploy new code | `cd /opt/lostfound && sudo git pull && lf up -d --build` |
| Database shell | `lf exec db psql -U lostfound -d lostfound` |
| Stop everything | `lf down` |

**Back up the database.** The data lives in a Docker volume on one disk with no
redundancy. A dump takes a second:

```bash
lf exec -T db pg_dump -U lostfound lostfound | gzip > ~/backup-$(date +%F).sql.gz
```

Nightly, via `sudo crontab -e`:

```
0 3 * * * docker compose -f /opt/lostfound/docker-compose.prod.yml --env-file /opt/lostfound/.env.prod exec -T db pg_dump -U lostfound lostfound | gzip > /home/ubuntu/backup-$(date +\%F).sql.gz
```

## Shutting it down

Stopping the instance halts compute charges but you still pay for the disk.
To stop paying entirely, terminate it — **this destroys the database**, so dump
first.

1. EC2 → Instances → select → **Instance state** → **Terminate**.
2. EC2 → **Elastic IPs** → release any you allocated. An unattached Elastic IP
   is billed precisely because it is idle.
3. EC2 → **Volumes** → confirm nothing orphaned remains.

## If you are on an AWS Academy Learner Lab

The lab stops your instance when the session ends and gives it a new public IP
on restart. Adjust as follows:

- **Skip Step 3's Elastic IP entirely** — Learner Labs usually block allocating
  one, and it would be released anyway.
- **After every "Start Lab"**: start the instance, copy the new public IP, paste
  it into DuckDNS, and wait a minute for DNS. The stack restarts by itself
  (`restart: unless-stopped`); Caddy reuses the certificate it already holds,
  since that is tied to the hostname, not the IP.
- **Expect roughly two minutes** of setup per session.
- **For the portfolio itself**, record a screen capture of the working site and
  put that in your README next to the architecture diagram. A recruiter will not
  wait for you to boot a lab, and a dead link is worse than no link. Keep the
  AWS deployment as the thing you talk through in an interview.

## When something breaks

**The site does not load at all.** Check the containers are up (`lf ps`), then
that the security group actually has ports 80 and 443 open to anywhere, then
that your IP has not changed if SSH also fails (the SSH rule is pinned to "My
IP", which moves when your home address does).

**Caddy cannot get a certificate.** Almost always DNS. Confirm
`dig +short <your-domain>` returns the instance's *current* public IP, and that
port 80 is open — Let's Encrypt verifies over HTTP even for an HTTPS
certificate. Read `lf logs caddy`. If you have failed many times in a row, you
may be rate limited for an hour; uncomment the `acme_ca` staging line in
`deploy/Caddyfile` to test without consuming quota.

**The build dies partway through, or the box goes unresponsive.** Out of
memory. Confirm swap exists with `free -h` — the Swap row should show 2 GiB. If
it is zero the bootstrap's swap step did not run; do it by hand from the script.

**The API restarts in a loop.** `lf logs api`. A `DATABASE_URL must point at
PostgreSQL` error means `.env.prod` is not being read — check you passed
`--env-file .env.prod`. An authentication failure against Postgres usually means
the password was regenerated after the data volume already existed; Postgres
only reads `POSTGRES_PASSWORD` when initialising an *empty* directory, so either
restore the original password or `lf down -v` and start over (destroying data).

**`docker: permission denied`.** The bootstrap added you to the `docker` group
but group membership only applies to new logins. Log out and back in, or use
`sudo`.
