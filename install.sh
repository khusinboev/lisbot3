#!/bin/bash

# License Bot Installation Script for Ubuntu Server
# Usage: ./install.sh

set -e

echo "=========================================="
echo "License Bot - O'rnatish skripti"
echo "=========================================="

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if running as root
if [ "$EUID" -eq 0 ]; then 
   echo -e "${RED}Xatolik: Root foydalanuvchi sifatida ishga tushirib bo'lmaydi${NC}"
   exit 1
fi

# Get current user
CURRENT_USER=$(whoami)
echo -e "${GREEN}Foydalanuvchi: $CURRENT_USER${NC}"

# Update system
echo -e "${YELLOW}Tizim yangilanmoqda...${NC}"
sudo apt-get update
sudo apt-get upgrade -y

# Install required packages
echo -e "${YELLOW}Kerakli paketlar o'rnatilmoqda...${NC}"
sudo apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    git \
    wget \
    curl \
    unzip \
    libnss3 \
    libatk-bridge2.0-0 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    libpangocairo-1.0-0 \
    libatspi2.0-0 \
    libgtk-3-0

# Create project directory
PROJECT_DIR="$HOME/license_bot"
echo -e "${YELLOW}Loyiha katalogi yaratilmoqda: $PROJECT_DIR${NC}"
mkdir -p "$PROJECT_DIR"

# Copy project files (assuming they are in current directory)
echo -e "${YELLOW}Loyiha fayllari nusxalanmoqda...${NC}"
cp -r . "$PROJECT_DIR/" 2>/dev/null || true

# Navigate to project directory
cd "$PROJECT_DIR"

# Create virtual environment
echo -e "${YELLOW}Virtual muhit yaratilmoqda...${NC}"
python3 -m venv venv

# Activate virtual environment
source venv/bin/activate

# Upgrade pip
echo -e "${YELLOW}pip yangilanmoqda...${NC}"
pip install --upgrade pip

# Install requirements
echo -e "${YELLOW}Python paketlari o'rnatilmoqda...${NC}"
pip install -r requirements.txt

# Install Playwright browsers
echo -e "${YELLOW}Playwright brauzerlari o'rnatilmoqda...${NC}"
playwright install chromium

# Create .env file if not exists
if [ ! -f ".env" ]; then
    echo -e "${YELLOW}.env fayli yaratilmoqda...${NC}"
    cp .env.example .env
    echo -e "${RED}DIQQAT: .env faylini tahrirlang va BOT_TOKEN ni qo'shing!${NC}"
fi

# Create data directory
mkdir -p data
mkdir -p downloads

# Setup systemd service
echo -e "${YELLOW}Systemd service sozlanmoqda...${NC}"
sudo cp license-bot.service "/etc/systemd/system/license-bot@$CURRENT_USER.service"

# Replace user in service file
sudo sed -i "s/%I/$CURRENT_USER/g" "/etc/systemd/system/license-bot@$CURRENT_USER.service"
sudo sed -i "s|/home/$CURRENT_USER|$HOME|g" "/etc/systemd/system/license-bot@$CURRENT_USER.service"

# Reload systemd
sudo systemctl daemon-reload

# Enable service
sudo systemctl "enable license-bot@$CURRENT_USER"

echo ""
echo "=========================================="
echo -e "${GREEN}O'rnatish yakunlandi!${NC}"
echo "=========================================="
echo ""
echo -e "${YELLOW}Keyingi qadamlar:${NC}"
echo "1. .env faylini tahrirlang:"
echo "   nano $PROJECT_DIR/.env"
echo ""
echo "2. BOT_TOKEN va ADMIN_IDS ni qo'shing"
echo ""
echo "3. Botni ishga tushiring:"
echo "   sudo systemctl start license-bot@$CURRENT_USER"
echo ""
echo "4. Holatini tekshiring:"
echo "   sudo systemctl status license-bot@$CURRENT_USER"
echo ""
echo "5. Loglarni ko'ring:"
echo "   sudo journalctl -u license-bot@$CURRENT_USER -f"
echo ""
echo "=========================================="
