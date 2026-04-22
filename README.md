# Auto Video Editor (Program B-Roll)

Auto Video Editor adalah aplikasi desktop berbasis Python dan PySide6 yang dirancang untuk mengotomatisasi proses pembuatan video. Aplikasi ini dapat mengubah skrip menjadi suara (TTS), menghasilkan transkrip, merencanakan b-roll menggunakan kecerdasan buatan (Google Gemini AI), mengunduh footage dari Pexels dan Pixabay secara otomatis, serta merender video akhir yang lengkap dengan subtitle dan efek teks melayang.

## 🌟 Fitur Utama

- **Pembuatan Voiceover (TTS):** Mendukung fitur Text-to-Speech untuk menghasilkan sulih suara otomatis dari skrip yang Anda ketik.
- **Transkripsi Otomatis:** Menghasilkan teks transkrip dari audio voiceover yang diberikan beserta timestamp-nya.
- **AI B-Roll Planner:** Memanfaatkan Google Gemini AI untuk menganalisis skrip/transkrip dan merancang konsep visual B-Roll.
- **Auto-Fetch Footage:** Terintegrasi dengan API Pexels dan Pixabay untuk mencari dan mengunduh aset video/gambar secara otomatis.
- **Review Panel Interaktif:** Memudahkan pengguna untuk meninjau dan mengedit aset sebelum render.
- **Rendering Cepat:** Menggunakan FFmpeg + hardware acceleration (QSV/NVENC).
- **Subtitle & Efek Teks:** Subtitle otomatis dan animasi teks.

## 📋 Alur Kerja (Workflow)

1. Input skrip atau audio  
2. Transkripsi otomatis  
3. AI planning (B-roll)  
4. Fetch footage  
5. Review & edit  
6. Render video akhir  

## 🛠️ Persyaratan Sistem

- Windows 10/11  
- Python 3.8+ (disarankan 3.10/3.11)   

## 🚀 Cara Instalasi & Menjalankan

### 🔹 Opsi 1: Menjalankan dengan Python (Source Code)

1. **Clone / Download repository**
2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```
3. **Jalankan aplikasi**
   ```bash
   python main.py
   ```

---

## ⚙️ Konfigurasi API Key

- Buka menu **Pengaturan (⚙️)** di aplikasi  
- Masukkan API berikut:
  - Google Gemini API Key  / service account vertex ai
  - Pexels API Key  
  - Pixabay API Key  
- Simpan konfigurasi  

---

## 📄 Lisensi

Menggunakan **MIT License**. Lihat file `LICENSE` untuk detail.