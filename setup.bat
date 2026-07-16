@echo off
echo ============================================
echo   Exness AutoTrader - Setup
echo ============================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found.
    echo Download Python 3.10+ from https://python.org
    echo Make sure to tick "Add Python to PATH" during install.
    pause & exit /b 1
)

echo [1/4] Creating virtual environment...
python -m venv venv
call venv\Scripts\activate.bat

echo [2/4] Upgrading pip...
python -m pip install --upgrade pip

echo [3/4] Installing dependencies...
pip install pandas numpy requests python-dotenv pytz colorama schedule scikit-learn joblib
pip install "python-telegram-bot>=13.0,<14.0"

echo [4/4] Installing MetaTrader5 (Windows only)...
pip install MetaTrader5

echo.
if not exist config\.env (
    copy config\.env.example config\.env
    echo >>> IMPORTANT: Open config\.env and fill in your details <<<
)
if not exist logs mkdir logs

echo.
echo ============================================
echo   Setup complete!
echo ============================================
echo.
echo NEXT STEPS:
echo   1. Open config\.env  ^(fill in MT5 login, password, server^)
echo   2. Open MetaTrader5 and log in to your Exness account
echo   3. In MT5: Tools ^> Options ^> Expert Advisors
echo              Tick "Allow automated trading"
echo   4. Run backtest:  python -m backtest.backtest_engine
echo   5. Start bot:     python main.py
echo.
pause
