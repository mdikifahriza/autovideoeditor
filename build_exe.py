import os
import sys
import PyInstaller.__main__

def build_exe():
    print("Mempersiapkan Build AutoVideoEditor...")
    
    # Cari ffmpeg dari imageio_ffmpeg
    try:
        import imageio_ffmpeg
        ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()
        print(f"Menggunakan FFmpeg lokal dari: {ffmpeg_path}")
    except ImportError:
        print("Gagal memuat imageio_ffmpeg! Pastikan sudah diinstal.")
        sys.exit(1)

    # Opsi build dasar untuk PyInstaller
    opts = [
        "main.py",
        "--name=AutoVideoEditor",
        "--onedir",       # Build sebagai satu folder (-D)
        "--windowed",     # Sembunyikan console (-w)
        "--clean",        # Bersihkan build lama
        "--noconfirm",    # Timpa kalau ada konfirmasi
    ]

    # Tambahkan ffmpeg ke root build folder exe
    opts.append(f"--add-binary={ffmpeg_path};.")

    # Tambahkan QSS stylesheet
    qss_src = os.path.join("gui", "style.qss")
    opts.append(f"--add-data={qss_src};gui")

    # Tambahkan icon jika Anda punya
    if os.path.exists("logo.ico"):
        opts.append("--icon=logo.ico")

    # Kumpulkan modul-modul dinamis yang mungkin tidak otomatis terbaca oleh PyInstaller
    hidden_imports = [
        "moviepy", 
        "numpy", 
        "imageio_ffmpeg", 
        "requests", 
        "keyring",
        "google.genai"
    ]
    for imp in hidden_imports:
        opts.append(f"--hidden-import={imp}")

    print(f"Menjalankan PyInstaller dengan argumen: {opts}")
    PyInstaller.__main__.run(opts)
    
    print("\n\n" + "="*50)
    print("Build Selesai!")
    print("Aplikasi Anda ada di folder: dist/AutoVideoEditor/")
    print("="*50)

if __name__ == "__main__":
    build_exe()
