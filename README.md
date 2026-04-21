# Auto Video Editor (Program B-Roll)

Auto Video Editor adalah aplikasi desktop berbasis Python dan PySide6 yang dirancang untuk mengotomatisasi proses pembuatan video. Aplikasi ini dapat mengubah skrip menjadi suara (TTS), menghasilkan transkrip, merencanakan b-roll menggunakan kecerdasan buatan (Google Gemini AI), mengunduh footage dari Pexels dan Pixabay secara otomatis, serta merender video akhir yang lengkap dengan subtitle dan efek teks melayang.

## 🌟 Fitur Utama

- **Pembuatan Voiceover (TTS):** Mendukung fitur Text-to-Speech untuk menghasilkan sulih suara otomatis dari skrip yang Anda ketik.
- **Transkripsi Otomatis:** Menghasilkan teks transkrip dari audio voiceover yang diberikan beserta timestamp-nya.
- **AI B-Roll Planner:** Memanfaatkan kehebatan Google Gemini AI untuk menganalisis skrip/transkrip dan memikirkan konsep visual B-Roll yang paling relevan.
- **Auto-Fetch Footage:** Terintegrasi langsung dengan API Pexels dan Pixabay untuk mencari dan mengunduh aset video/gambar secara otomatis.
- **Review Panel Interaktif:** Antarmuka (GUI) yang memudahkan pengguna untuk meninjau, mengubah, dan menyetujui aset b-roll per segmen sebelum mulai di-render.
- **Rendering Cepat (Hardware Acceleration):** Menggunakan FFmpeg dan MoviePy dengan dukungan akselerasi perangkat keras (QSV/NVENC) untuk ekspor video yang lebih efisien.
- **Subtitle & Efek Teks:** Menyediakan opsi untuk membuat subtitle otomatis dan efek animasi teks melayang (floating text) untuk meningkatkan retensi dan visual video.

## 📋 Alur Kerja (Workflow)

1. **Upload/Input:** Anda memulai dengan mengunggah file audio voiceover atau mengetikkan skrip manual untuk dibuatkan audio TTS.
2. **Transkripsi:** Sistem akan memproses audio untuk mendapatkan teks transkrip yang selaras dengan waktu tayang (timestamp).
3. **AI Planning:** Gemini AI menganalisis transkrip dan merumuskan kata kunci pencarian b-roll untuk setiap segmen video.
4. **Fetching B-Roll:** Sistem secara otomatis akan mencari dan mengunduh aset video atau gambar dari Pexels/Pixabay yang sesuai dengan rekomendasi AI.
5. **Review & Refine:** Anda dapat meninjau hasil pencarian B-Roll di antarmuka *Review Panel*. Di sini, Anda bebas untuk menukar aset, mencari secara manual, atau menyesuaikan durasi.
6. **Rendering:** Setelah seluruh segmen disetujui, sistem akan memproses (render) penggabungan audio, b-roll, subtitle, dan efek lainnya menjadi satu video utuh siap pakai.

## 🛠️ Persyaratan Sistem

- **OS:** Windows 10/11
- **Python:** Versi 3.8 atau lebih baru (Disarankan 3.10/3.11)
- **FFmpeg:** Wajib diinstal dan terdaftar ke dalam System Environment Variables (PATH).

## 🚀 Cara Instalasi

1. **Clone atau Unduh Repository ini:**
   Ekstrak file/folder di direktori pilihan Anda.

2. **Jalankan Installer Otomatis:**
   Klik ganda pada file `install.bat`. Skrip ini akan secara otomatis:
   - Memastikan Python sudah terinstal di komputer.
   - Menginstal semua pustaka/dependensi yang diperlukan (seperti `moviepy`, `PySide6`, `google-generativeai`, `requests`, dll).
   - Mengecek ketersediaan FFmpeg di sistem.

3. **Instalasi FFmpeg (Jika belum ada):**
   Apabila installer mendeteksi FFmpeg belum ada, silakan ikuti panduan berikut:
   - Unduh FFmpeg dari [Gyan.dev (ffmpeg-release-essentials.zip)](https://www.gyan.dev/ffmpeg/builds/).
   - Ekstrak isi file .zip tersebut ke `C:\ffmpeg\`.
   - Tambahkan jalur/path `C:\ffmpeg\bin` ke dalam **System PATH** Windows Anda.
   - Buka ulang CMD atau jalankan ulang `install.bat` untuk verifikasi.

## ⚙️ Cara Penggunaan

1. **Jalankan Aplikasi:**
   Buka terminal atau Command Prompt di dalam folder proyek, lalu jalankan perintah:
   ```bash
   python main.py
   ```
2. **Konfigurasi API Keys:**
   - Setelah aplikasi terbuka, navigasikan ke menu **Pengaturan** (Biasanya berlogo Ikon Gear ⚙️).
   - Masukkan **API Key** yang diperlukan untuk mengaktifkan fitur otomatisasi:
     - **Google Gemini API Key** (Dibutuhkan untuk fitur AI Planner)
     - **Pexels API Key** (Dibutuhkan untuk Auto-Fetch Footage)
     - **Pixabay API Key** (Sebagai sumber sekunder B-Roll)
   - Simpan pengaturan.
3. **Mulai Memulai Proyek:**
   - Mulai dengan memasukkan Skrip atau Audio Voiceover pada panel awal.
   - Ikuti proses langkah demi langkah dari aplikasi hingga tahap *Review*.
   - Sesuaikan footage jika perlu, dan klik tombol **Render** untuk menghasilkan video akhir Anda!

## 📄 Lisensi

Proyek ini menggunakan lisensi **MIT License**. Silakan merujuk ke file `LICENSE` untuk rincian lebih lanjut.
