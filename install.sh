#!/bin/bash
# ──────────────────────────────────────────────────────────────────────────────
# License Bot — Ubuntu Server O'rnatish Skripti
# Foydalanish: chmod +x install.sh && ./install.sh
# ──────────────────────────────────────────────────────────────────────────────

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

info()    { echo -e "${BLUE}[INFO]${NC} $1"; }
success() { echo -e "${GREEN}[OK]${NC} $1"; }
warn()    { echo -e "${YELLOW}[WARN]${NC} $1"; }
error()   { echo -e "${RED}[XATO]${NC} $1"; exit 1; }

echo ""
echo "══════════════════════════════════════════════"
echo "  License Bot — O'rnatish"
echo "══════════════════════════════════════════════"
echo ""

# ── 1. Tizim paketlari ────────────────────────────────────────────────────────
info "Tizim yangilanmoqda..."
apt-get update -qq
apt-get install -y -qq \
    python3 python3-pip python3-venv git wget curl \
    xvfb \
    libnss3 libatk-bridge2.0-0 libxcomposite1 libxdamage1 \
    libxrandr2 libgbm1 libasound2 libpangocairo-1.0-0 \
    libatspi2.0-0 libgtk-3-0 libxss1
success "Tizim paketlari o'rnatildi"

# ── 2. Google Chrome ──────────────────────────────────────────────────────────
if ! command -v google-chrome &>/dev/null; then
    info "Google Chrome o'rnatilmoqda..."
    wget -q https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb -O /tmp/chrome.deb
    apt-get install -y -qq /tmp/chrome.deb
    rm /tmp/chrome.deb
    success "Google Chrome o'rnatildi: $(google-chrome --version)"
else
    success "Google Chrome mavjud: $(google-chrome --version)"
fi

# ── 3. Loyiha papkasi ─────────────────────────────────────────────────────────
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
info "Loyiha papkasi: $PROJECT_DIR"

mkdir -p "$PROJECT_DIR/data"
mkdir -p "$PROJECT_DIR/downloads"
mkdir -p "$PROJECT_DIR/data/chrome_profile_parser_v3"

# ── 4. Virtual muhit ─────────────────────────────────────────────────────────
info "Python virtual muhit yaratilmoqda..."
python3 -m venv "$PROJECT_DIR/.venv"
source "$PROJECT_DIR/.venv/bin/activate"
pip install --upgrade pip -q
pip install -r "$PROJECT_DIR/requirements.txt" -q
success "Python paketlari o'rnatildi"

# ── 5. .env fayl ─────────────────────────────────────────────────────────────
if [ ! -f "$PROJECT_DIR/.env" ]; then
    cp "$PROJECT_DIR/.env.example" "$PROJECT_DIR/.env"
    warn ".env fayli yaratildi — BOT_TOKEN va ADMIN_IDS ni kiriting:"
    warn "  nano $PROJECT_DIR/.env"
else
    info ".env fayli mavjud"
fi

# ── 6. Xvfb service ──────────────────────────────────────────────────────────
info "Xvfb service yaratilmoqda..."
cat > /etc/systemd/system/xvfb.service << EOF
[Unit]
Description=Virtual Frame Buffer X Server
After=network.target

[Service]
Type=simple
ExecStartPre=/bin/sh -c 'rm -f /tmp/.X99-lock'
ExecStart=/usr/bin/Xvfb :99 -screen 0 1920x1080x24 -ac
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable xvfb
systemctl start xvfb || warn "Xvfb ishga tushmadi (allaqachon ishlayotgan bo'lishi mumkin)"
success "Xvfb service sozlandi"

# ── 7. Bot service ────────────────────────────────────────────────────────────
info "Bot systemd service yaratilmoqda..."
CURRENT_USER=$(whoami)

cat > /etc/systemd/system/license-bot.service << EOF
[Unit]
Description=License Bot - Telegram Bot for license.gov.uz
After=network.target xvfb.service
Wants=xvfb.service

[Service]
Type=simple
User=$CURRENT_USER
WorkingDirectory=$PROJECT_DIR
Environment=PATH=$PROJECT_DIR/.venv/bin
Environment=DISPLAY=:99
EnvironmentFile=$PROJECT_DIR/.env
ExecStart=$PROJECT_DIR/.venv/bin/python main.py
Restart=always
RestartSec=15
StandardOutput=journal
StandardError=journal
SyslogIdentifier=license-bot

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable license-bot
success "Bot service sozlandi"

# ── Yakuniy ───────────────────────────────────────────────────────────────────
echo ""
echo "══════════════════════════════════════════════"
echo -e "${GREEN}  O'rnatish yakunlandi!${NC}"
echo "══════════════════════════════════════════════"
echo ""
echo "Keyingi qadamlar:"
echo ""
echo "  1. .env faylini tahrirlang:"
echo "     nano $PROJECT_DIR/.env"
echo ""
echo "  2. BOT_TOKEN va ADMIN_IDS ni kiriting"
echo ""
echo "  3. Botni ishga tushiring:"
echo "     systemctl start license-bot"
echo ""
echo "  4. Holatni tekshiring:"
echo "     systemctl status license-bot"
echo ""
echo "  5. Loglarni ko'ring:"
echo "     journalctl -u license-bot -f"
echo ""