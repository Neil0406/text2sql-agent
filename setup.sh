#!/usr/bin/env bash
# =============================================================================
# Text2SQL Agent - Environment Setup Script
# Supports: macOS / Linux

# ./setup.sh
#     │
#     ├─ Step 1：偵測 macOS / Linux
#     │
#     ├─ Step 2：檢查 Ollama 有沒有裝
#     │           沒有 → 自動用 brew 或 curl 安裝
#     │           有   → 跳過
#     │
#     ├─ Step 3：檢查 gemma4:e4b 模型有沒有下載
#     │           沒有 → ollama pull gemma4:e4b
#     │           有   → 跳過
#     │
#     ├─ Step 4：驗證模型能不能推論
#     │           跑一個簡單測試，失敗就中止
#     │
#     ├─ Step 5：確認 Python 版本 >= 3.11
#     │           不符合 → 報錯並告知解法，中止
#     │           符合   → pip install -r requirements.txt
#     │
#     ├─ 建立 .env（從 .env.example 複製）
#     │
#     └─ 初始化 SQLite DB（如果 CSV 已放好的話）
# =============================================================================
set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info()    { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[ OK ]${NC} $1"; }
log_warn()    { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error()   { echo -e "${RED}[ERR ]${NC} $1"; }

OLLAMA_MODEL="${OLLAMA_MODEL:-gemma4:e4b}"

echo "======================================================"
echo "   Text2SQL AI Agent — Environment Setup"
echo "======================================================"
echo ""

# ─── Step 1: Detect Platform ────────────────────────────────────────────────
log_info "Step 1: Detecting system platform..."
OS="$(uname -s 2>/dev/null || echo Unknown)"
case "$OS" in
  Darwin*) PLATFORM="macOS" ;;
  Linux*)  PLATFORM="Linux" ;;
  MINGW*|CYGWIN*|MSYS*) PLATFORM="Windows" ;;
  *) PLATFORM="Unknown" ;;
esac
log_success "Platform: $PLATFORM"

if [[ "$PLATFORM" == "Windows" ]]; then
  log_error "Windows detected. Please use WSL (Windows Subsystem for Linux) or run setup.bat."
  exit 1
fi

if [[ "$PLATFORM" == "Unknown" ]]; then
  log_warn "Unknown platform — continuing anyway."
fi

# ─── Step 2: Check / Install Ollama ────────────────────────────────────────
log_info "Step 2: Checking Ollama installation..."
if command -v ollama &>/dev/null; then
  OLLAMA_VER=$(ollama --version 2>/dev/null | head -1 || echo "unknown")
  log_success "Ollama already installed: $OLLAMA_VER"
else
  log_warn "Ollama not found. Installing..."
  if [[ "$PLATFORM" == "macOS" ]]; then
    if command -v brew &>/dev/null; then
      log_info "Installing via Homebrew..."
      brew install --cask ollama
    else
      log_info "Downloading Ollama installer from ollama.com..."
      curl -fsSL https://ollama.com/install.sh | sh
    fi
  else
    log_info "Downloading Ollama installer..."
    curl -fsSL https://ollama.com/install.sh | sh
  fi
  log_success "Ollama installed successfully."
fi

# Start Ollama service if not running
if ! pgrep -x "ollama" &>/dev/null; then
  log_info "Starting Ollama service..."
  if [[ "$PLATFORM" == "macOS" ]]; then
    open -a Ollama 2>/dev/null || (ollama serve &>/tmp/ollama.log &)
  else
    ollama serve &>/tmp/ollama.log &
  fi
  sleep 4
  log_success "Ollama service started."
else
  log_success "Ollama service already running."
fi

# ─── Step 3: Check / Pull Model ─────────────────────────────────────────────
log_info "Step 3: Checking model [ ${OLLAMA_MODEL} ]..."
if ollama list 2>/dev/null | grep -q "$(echo ${OLLAMA_MODEL} | cut -d: -f1)"; then
  log_success "Model ${OLLAMA_MODEL} already downloaded."
else
  log_warn "Model ${OLLAMA_MODEL} not found. Pulling (this may take several minutes)..."
  log_info "Estimated size: ~5 GB (INT4 quantization)"
  if ! ollama pull "${OLLAMA_MODEL}"; then
    log_error "Failed to pull ${OLLAMA_MODEL}. Trying gemma3:4b as fallback..."
    if ollama pull gemma3:4b; then
      OLLAMA_MODEL="gemma3:4b"
      sed -i.bak "s/OLLAMA_MODEL=.*/OLLAMA_MODEL=${OLLAMA_MODEL}/" .env 2>/dev/null || true
      log_success "Fallback model ready: ${OLLAMA_MODEL}"
    else
      log_error "Failed to pull fallback model gemma3:4b as well."
      log_error "Please check your network connection and Ollama service, then re-run."
      exit 1
    fi
  else
    log_success "Model ready: ${OLLAMA_MODEL}"
  fi
fi

# ─── Step 4: Verify Inference ───────────────────────────────────────────────
log_info "Step 4: Verifying model inference..."
TEST_OUT=$(echo "Reply with the single word: READY" | ollama run "${OLLAMA_MODEL}" --nowordwrap 2>/dev/null | head -c 80 || echo "")
if [[ -n "$TEST_OUT" ]]; then
  log_success "Inference OK: ${TEST_OUT:0:60}"
else
  log_error "Inference test failed. Check Ollama logs at /tmp/ollama.log"
  exit 1
fi

# ─── Step 5: Python & Dependencies ──────────────────────────────────────────
log_info "Step 5: Checking Python environment..."
if ! command -v python3 &>/dev/null; then
  log_error "Python 3 not found. Please install Python 3.10+ and retry."
  exit 1
fi
PY_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
log_info "Python version: $PY_VER"

REQUIRED_MAJOR=3; REQUIRED_MINOR=11
ACTUAL_MAJOR=$(echo $PY_VER | cut -d. -f1)
ACTUAL_MINOR=$(echo $PY_VER | cut -d. -f2)
if [[ "$ACTUAL_MAJOR" -lt "$REQUIRED_MAJOR" ]] || { [[ "$ACTUAL_MAJOR" -eq "$REQUIRED_MAJOR" ]] && [[ "$ACTUAL_MINOR" -lt "$REQUIRED_MINOR" ]]; }; then
  log_error "Python $REQUIRED_MAJOR.$REQUIRED_MINOR+ is required (found $PY_VER)."
  log_error "langchain>=0.3.0 does not support Python < 3.11."
  log_error "Please activate a Python 3.11+ environment first, e.g.:"
  log_error "  conda create -n text2sql-agent python=3.11 -y"
  log_error "  conda activate text2sql-agent"
  log_error "Then re-run: ./setup.sh"
  exit 1
fi

log_info "Installing Python dependencies..."
python3 -m pip install --upgrade pip -q
python3 -m pip install -r requirements.txt
log_success "Python dependencies installed."

# ─── Setup .env ─────────────────────────────────────────────────────────────
if [[ ! -f ".env" ]]; then
  cp .env.example .env
  log_info "Created .env from .env.example"
  log_warn "Edit .env and add your LANGSMITH_API_KEY for tracing support."
fi

# Ensure OLLAMA_MODEL is set in .env
if ! grep -q "OLLAMA_MODEL" .env 2>/dev/null; then
  echo "OLLAMA_MODEL=${OLLAMA_MODEL}" >> .env
fi

# ─── Initialize Database ────────────────────────────────────────────────────
log_info "Checking dataset and database..."
CSV_PATH="data/SuperMarket Analysis.csv"
DB_PATH="data/supermarket.db"

if [[ -f "$CSV_PATH" ]]; then
  if [[ ! -f "$DB_PATH" ]]; then
    log_info "Initializing SQLite database from CSV..."
    python3 src/db/init_db.py
    log_success "Database initialized at $DB_PATH"
  else
    log_success "Database already exists at $DB_PATH"
  fi
else
  log_warn "Dataset not found at: $CSV_PATH"
  log_warn "Please download from Kaggle:"
  log_warn "  https://www.kaggle.com/datasets/faresashraf1001/supermarket-sales"
  log_warn "Place the CSV at: $CSV_PATH"
fi

# ─── Done ───────────────────────────────────────────────────────────────────
echo ""
echo "======================================================"
echo -e "${GREEN}  Environment setup complete!${NC}"
echo "======================================================"
echo ""
echo "Next steps:"
echo "  1. Download dataset to: data/SuperMarket Analysis.csv"
echo "  2. Add LANGSMITH_API_KEY to .env (optional, for tracing)"
echo "  3. Run CLI:         python3 src/main.py"
echo "  4. Run Web UI:      streamlit run src/app.py"
echo ""
