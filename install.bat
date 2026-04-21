@echo off
echo ============================================
echo   AUTO VIDEO EDITOR v2 - INSTALLER
echo ============================================
echo.

echo [1/3] Cek Python...
python --version
if errorlevel 1 (
    echo ERROR: Python tidak ditemukan! Download di python.org
    pause & exit /b 1
)

echo.
echo [2/3] Install dependencies...
pip install moviepy requests PySide6 numpy google-generativeai keyring psutil imageio-ffmpeg

echo.
echo [3/3] Cek FFmpeg...
ffmpeg -version >nul 2>&1
if errorlevel 1 (
    echo.
    echo FFmpeg belum terinstall!
    echo 1. Download: https://www.gyan.dev/ffmpeg/builds/
    echo    Pilih: ffmpeg-release-essentials.zip
    echo 2. Extract ke C:\ffmpeg\
    echo 3. Tambah C:\ffmpeg\bin ke System PATH
    echo 4. Restart CMD, jalankan install.bat lagi
    pause & exit /b 1
) else (
    echo FFmpeg OK
)

echo.
echo ============================================
echo   INSTALASI SELESAI!
echo ============================================
echo.
echo SEBELUM MULAI:
echo 1. Jalankan aplikasi dengan perintah: python main.py
echo 2. Buka menu [⚙️ Pengaturan] di aplikasi
echo 3. Masukkan API Key untuk Gemini, Pexels, dan Pixabay
echo.
pause   