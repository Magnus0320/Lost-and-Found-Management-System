#!/usr/bin/env bash
#
# First-boot provisioning for a fresh Ubuntu 24.04 EC2 instance.
#
# Paste this into the "User data" box when launching the instance and AWS runs
# it as root on first boot. You can also run it by hand over SSH:
#     sudo bash bootstrap-ec2.sh
#
# It is safe to re-run: every step checks whether it has already been done.
# Progress is written to /var/log/cloud-init-output.log -- read it with
#     sudo tail -f /var/log/cloud-init-output.log
#
# ---------------------------------------------------------------------------
# EDIT THESE THREE LINES BEFORE LAUNCHING
# ---------------------------------------------------------------------------

# Your repository. Must be public, or the clone below will hang asking for a
# password that nobody is there to type.
REPO_URL="https://github.com/Magnus0320/Lost-and-Found-Management-System.git"
REPO_BRANCH="main"

# The hostname visitors will use. Leave EMPTY to serve plain HTTP on the
# instance's IP address while you are still testing; set it to a real
# hostname (e.g. campus-lostfound.duckdns.org) and Caddy will fetch a free
# Let's Encrypt certificate on startup. The DNS record must already point at
# this instance before you set it, or the certificate request will fail.
SITE_ADDRESS=""

# Where Let's Encrypt sends expiry warnings. Only used when SITE_ADDRESS is set.
ACME_EMAIL=""

# ---------------------------------------------------------------------------

set -euo pipefail

# Let's Encrypt rejects placeholder addresses such as admin@example.invalid,
# so a hostname without a real contact email would boot with no certificate.
if [ -n "$SITE_ADDRESS" ] && [ -z "$ACME_EMAIL" ]; then
	echo "ACME_EMAIL must be a real address when SITE_ADDRESS is set" >&2
	exit 1
fi

APP_DIR="/opt/lostfound"
LOGIN_USER="ubuntu"

log() { echo "=== [bootstrap] $* ==="; }

# --- 1. Wait for the automatic-updates lock -------------------------------
# Ubuntu images run unattended-upgrades on first boot. Racing it produces the
# classic "Could not get lock /var/lib/dpkg/lock-frontend" failure, so wait.
log "Waiting for apt locks to clear"
for _ in $(seq 1 60); do
	if ! fuser /var/lib/dpkg/lock-frontend >/dev/null 2>&1 &&
		! fuser /var/lib/apt/lists/lock >/dev/null 2>&1; then
		break
	fi
	sleep 5
done

# --- 2. Swap --------------------------------------------------------------
# The free-tier instance has 1 GiB of RAM. Building the Python image and
# running Postgres alongside it will exhaust that and the kernel will kill the
# build partway through, which looks like a mysterious hang. Swap is the fix.
if [ ! -f /swapfile ]; then
	log "Creating 2 GiB swap file"
	fallocate -l 2G /swapfile || dd if=/dev/zero of=/swapfile bs=1M count=2048
	chmod 600 /swapfile
	mkswap /swapfile
	swapon /swapfile
	echo '/swapfile none swap sw 0 0' >>/etc/fstab
	# Prefer RAM, but allow spilling rather than dying.
	sysctl -w vm.swappiness=10
	echo 'vm.swappiness=10' >/etc/sysctl.d/99-swappiness.conf
else
	log "Swap already present, skipping"
fi

# --- 3. Docker ------------------------------------------------------------
if ! command -v docker >/dev/null 2>&1; then
	log "Installing Docker from Docker's official repository"
	export DEBIAN_FRONTEND=noninteractive
	apt-get update -y
	apt-get install -y ca-certificates curl gnupg git

	install -m 0755 -d /etc/apt/keyrings
	curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
		-o /etc/apt/keyrings/docker.asc
	chmod a+r /etc/apt/keyrings/docker.asc

	# shellcheck disable=SC1091
	echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
		>/etc/apt/sources.list.d/docker.list

	apt-get update -y
	apt-get install -y docker-ce docker-ce-cli containerd.io \
		docker-buildx-plugin docker-compose-plugin

	systemctl enable --now docker
	# So you can run `docker ...` over SSH without sudo. Takes effect on your
	# next login, not the current shell.
	usermod -aG docker "$LOGIN_USER" || true
else
	log "Docker already installed, skipping"
fi

# --- 4. Source code -------------------------------------------------------
if [ ! -d "$APP_DIR/.git" ]; then
	log "Cloning $REPO_URL ($REPO_BRANCH)"
	git clone --branch "$REPO_BRANCH" --depth 1 "$REPO_URL" "$APP_DIR"
else
	log "Repository already present, pulling latest"
	git -C "$APP_DIR" fetch --depth 1 origin "$REPO_BRANCH"
	git -C "$APP_DIR" reset --hard "origin/$REPO_BRANCH"
fi
chown -R "$LOGIN_USER:$LOGIN_USER" "$APP_DIR"

# --- 5. Secrets -----------------------------------------------------------
# Generated once and then left alone. Regenerating SECRET_KEY would invalidate
# every issued JWT; regenerating the database password would lock the API out
# of the existing pgdata volume, because Postgres only reads POSTGRES_PASSWORD
# when it initialises an empty data directory.
ENV_FILE="$APP_DIR/.env.prod"
if [ ! -f "$ENV_FILE" ]; then
	log "Generating $ENV_FILE with fresh random secrets"
	cat >"$ENV_FILE" <<EOF
# Generated by bootstrap-ec2.sh on $(date -u +%Y-%m-%dT%H:%M:%SZ).
# Treat this file as a password. It is gitignored and must stay that way.

POSTGRES_USER=lostfound
POSTGRES_PASSWORD=$(openssl rand -hex 32)
POSTGRES_DB=lostfound

SECRET_KEY=$(openssl rand -hex 48)
ACCESS_TOKEN_EXPIRE_MINUTES=720
OTP_TTL_MINUTES=10

# Empty means plain HTTP on port 80. A hostname turns on automatic HTTPS.
SITE_ADDRESS=$SITE_ADDRESS
ACME_EMAIL=$ACME_EMAIL

# With mail disabled the API returns the one-time code as \`otp_debug\`, so a
# visitor can complete registration without any mail server. Turning this on
# makes otp_debug null and requires the MAIL_* values below.
MAIL_ENABLED=false
MAIL_SERVER=
MAIL_PORT=587
MAIL_USERNAME=
MAIL_PASSWORD=
MAIL_FROM=no-reply@campus-lost-found.local
MAIL_USE_TLS=true
EOF
	chmod 600 "$ENV_FILE"
	chown "$LOGIN_USER:$LOGIN_USER" "$ENV_FILE"
else
	log "$ENV_FILE already exists, leaving its secrets untouched"
fi

# --- 6. Build and start ---------------------------------------------------
log "Building and starting the stack (first build takes 3-6 minutes)"
cd "$APP_DIR"
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build

# --- 7. Verify ------------------------------------------------------------
log "Waiting for the API to report healthy"
for i in $(seq 1 60); do
	if curl -fsS http://127.0.0.1/health >/dev/null 2>&1; then
		log "Healthy after ${i}0 seconds"
		curl -fsS http://127.0.0.1/health
		echo
		break
	fi
	sleep 10
done

docker compose -f docker-compose.prod.yml --env-file .env.prod ps
log "Bootstrap finished"
